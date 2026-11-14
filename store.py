"""Foydalanuvchi ma'lumotlari ombori (v8).

Asosiy ma'lumot xotirada (tez), yozuvlar esa fonda Upstash Redis (REST) bazasiga ketadi.
UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN berilmasa — faqat xotira (v7 kabi).
Baza ishlamay qolsa ham bot to'xtamaydi: xato logga yoziladi, xotira bilan davom etadi.
Buyruqlar soni kam bo'lishi uchun: foydalanuvchi har jarayon umri uchun 1 marta yuklanadi,
'faollik' kuniga 1 marta yoziladi.
"""
import asyncio
import collections
import datetime
import logging
import os

log = logging.getLogger("store")
DAY = 86400


def _today():
    return datetime.date.today().isoformat()


def _pairs(flat):
    """HGETALL natijasi: ['k','v','k','v'] yoki dict -> dict."""
    if not flat:
        return {}
    if isinstance(flat, dict):
        return dict(flat)
    return dict(zip(flat[::2], flat[1::2]))


class Upstash:
    """Upstash Redis REST: har bir buyruq — JSON massiv, ko'p buyruq — /pipeline."""

    def __init__(self, url, token):
        self.url, self.token, self._c = url.rstrip("/"), token, None

    @classmethod
    def from_env(cls):
        url, token = os.getenv("UPSTASH_REDIS_REST_URL"), os.getenv("UPSTASH_REDIS_REST_TOKEN")
        return cls(url, token) if url and token else None

    async def pipe(self, cmds):
        import httpx

        if self._c is None:
            self._c = httpx.AsyncClient(timeout=10, headers={"Authorization": f"Bearer {self.token}"})
        r = await self._c.post(self.url + "/pipeline", json=[[str(a) for a in c] for c in cmds])
        r.raise_for_status()
        return [x.get("result") for x in r.json()]


class Store:
    def __init__(self, backend=None, prefix=None):
        self.db = backend
        self.p = prefix if prefix is not None else os.getenv("STORE_PREFIX", "clooer:")
        self.users, self.profiles = {}, {}
        self.used_cache = {}          # (uid, kind, sana) -> son
        self.optout, self.blocked, self.loaded = set(), set(), set()
        self.made, self.rates = collections.Counter(), collections.Counter()
        self.started = datetime.datetime.now()
        self._tasks = set()

    # ---------- fon yozuvi ----------
    def _bg(self, *cmds):
        if not self.db or not cmds:
            return
        t = asyncio.get_running_loop().create_task(self._run(list(cmds)))
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    async def _run(self, cmds):
        try:
            await self.db.pipe(cmds)
        except Exception as e:  # baza ishlamasa ham bot davom etadi
            log.warning("Baza yozuvi xatosi: %s", e)

    def k(self, *parts):
        return self.p + ":".join(str(x) for x in parts)

    # ---------- foydalanuvchi ----------
    async def seen(self, u):
        uid, today = u.id, _today()
        rec = self.users.setdefault(uid, {})
        rec["name"] = getattr(u, "full_name", "") or rec.get("name", "")
        rec["username"] = getattr(u, "username", None) or rec.get("username", "")
        rec["last"] = datetime.datetime.now()
        if uid not in self.loaded:
            self.loaded.add(uid)
            if self.db:
                try:
                    res = await self.db.pipe([
                        ("HGETALL", self.k("profile", uid)),
                        ("GET", self.k("use", "doc", uid, today)),
                        ("GET", self.k("use", "chat", uid, today)),
                        ("SISMEMBER", self.k("optout"), uid),
                    ])
                    if res[0]:
                        self.profiles[uid] = _pairs(res[0])
                    self.used_cache[(uid, "doc", today)] = int(res[1] or 0)
                    self.used_cache[(uid, "chat", today)] = int(res[2] or 0)
                    if res[3]:
                        self.optout.add(uid)
                except Exception as e:
                    log.warning("Foydalanuvchini yuklab bo‘lmadi: %s", e)
        if rec.get("day") != today:
            rec["day"] = today
            self._bg(("SADD", self.k("users"), uid),
                     ("HSET", self.k("user", uid), "name", rec["name"], "username", rec["username"] or "",
                      "last", datetime.datetime.now().isoformat(timespec="seconds")),
                     ("SADD", self.k("active", today), uid),
                     ("EXPIRE", self.k("active", today), 3 * DAY))

    # ---------- kunlik limit ----------
    def used(self, uid, kind):
        return self.used_cache.get((uid, kind, _today()), 0)

    def add_used(self, uid, kind):
        key = (uid, kind, _today())
        self.used_cache[key] = self.used_cache.get(key, 0) + 1
        redis_key = self.k("use", kind, uid, key[2])
        self._bg(("INCR", redis_key), ("EXPIRE", redis_key, 2 * DAY))

    # ---------- profil ----------
    def profile(self, uid):
        return dict(self.profiles.get(uid, {}))

    def set_profile(self, uid, **kw):
        if not kw:
            return
        self.profiles.setdefault(uid, {}).update(kw)
        flat = [x for kv in kw.items() for x in kv]
        self._bg(("HSET", self.k("profile", uid), *flat), ("SADD", self.k("profiled"), uid))

    def clear_profile(self, uid):
        self.profiles.pop(uid, None)
        self._bg(("DEL", self.k("profile", uid)), ("SREM", self.k("profiled"), uid))

    def save_from_form(self, uid, keys, data):
        """Formadagi javoblarni profilga saqlaydi. O'zgargan kalitlar ro'yxatini qaytaradi."""
        prof = self.profiles.get(uid, {})
        new = {}
        for key in keys:
            v = (data.get(key) or "").strip()
            if v and v not in ("-", "—") and prof.get(key) != v:
                new[key] = v
        self.set_profile(uid, **new)
        return list(new)

    # ---------- e'lonlar ----------
    def is_optout(self, uid):
        return uid in self.optout

    def set_optout(self, uid, flag):
        (self.optout.add if flag else self.optout.discard)(uid)
        self._bg(("SADD" if flag else "SREM", self.k("optout"), uid))

    def mark_blocked(self, uid):
        self.blocked.add(uid)
        self._bg(("SADD", self.k("blocked"), uid))

    async def broadcast_ids(self):
        """E'lon yuboriladigan foydalanuvchilar: hamma - bloklaganlar - voz kechganlar."""
        if self.db:
            try:
                users, blocked, opt = await self.db.pipe([
                    ("SMEMBERS", self.k("users")), ("SMEMBERS", self.k("blocked")), ("SMEMBERS", self.k("optout"))])
                ids = {int(x) for x in (users or [])}
                return sorted(ids - {int(x) for x in (blocked or [])} - {int(x) for x in (opt or [])}
                              - self.blocked - self.optout)
            except Exception as e:
                log.warning("Ro‘yxatni olib bo‘lmadi: %s", e)
        return sorted(set(self.users) - self.blocked - self.optout)

    # ---------- statistika ----------
    def count(self, form):
        self.made[form] += 1
        self._bg(("HINCRBY", self.k("stats", "made"), form, 1))

    def rate(self, form, up):
        v = "up" if up else "down"
        self.rates[(form, v)] += 1
        self._bg(("HINCRBY", self.k("stats", "rate"), f"{form}:{v}", 1))

    async def stats_text(self):
        today = _today()
        made, rates = self.made, self.rates
        users, active, profiled, blocked, opt = (len(self.users), sum(
            1 for r in self.users.values() if r["last"].date() == datetime.date.today()),
            len(self.profiles), len(self.blocked), len(self.optout))
        where = "xotira (baza ulanmagan)"
        if self.db:
            try:
                r = await self.db.pipe([
                    ("SCARD", self.k("users")), ("SCARD", self.k("active", today)), ("SCARD", self.k("profiled")),
                    ("HGETALL", self.k("stats", "made")), ("HGETALL", self.k("stats", "rate")),
                    ("SCARD", self.k("blocked")), ("SCARD", self.k("optout"))])
                users, active, profiled, blocked, opt = (int(r[0] or 0), int(r[1] or 0), int(r[2] or 0),
                                                         int(r[5] or 0), int(r[6] or 0))
                made = collections.Counter({k: int(v) for k, v in _pairs(r[3]).items()})
                rates = collections.Counter()
                for k, v in _pairs(r[4]).items():
                    f, _, d = k.rpartition(":")
                    rates[(f, d)] = int(v)
                where = "Upstash Redis ✅"
            except Exception as e:
                log.warning("Statistika bazadan olinmadi: %s", e)
                where = "xotira (baza xatosi ⚠️)"
        lines = [f"📊 Statistika | Saqlash: {where}",
                 f"👥 Foydalanuvchilar: {users} (bugun faol: {active})",
                 f"👤 Profil saqlaganlar: {profiled}",
                 f"📢 E’lonni bloklagan/voz kechgan: {blocked}/{opt}"]
        if made:
            lines.append("📄 Tayyorlangan: " + ", ".join(f"{k} {v}" for k, v in made.most_common()))
        forms = sorted({f for f, _ in rates})
        if forms:
            lines.append("⭐ Baholar: " + ", ".join(
                f"{f} 👍{rates[(f, 'up')]}/👎{rates[(f, 'down')]}" for f in forms))
        return "\n".join(lines)


store = Store(Upstash.from_env())
