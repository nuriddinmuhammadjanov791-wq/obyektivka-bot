"""Foydalanuvchi ma'lumotlari ombori. Hozircha XOTIRADA (bot qayta ishga tushsa tozalanadi).
v8 da shu interfeys tashqi bazaga ulanadi — bot.py o'zgarmaydi."""
import collections
import datetime


class Store:
    def __init__(self):
        self.users = {}
        self.profiles = {}
        self.made = collections.Counter()
        self.rates = collections.Counter()
        self.started = datetime.datetime.now()

    def touch(self, u):
        now = datetime.datetime.now()
        rec = self.users.setdefault(u.id, {"first": now, "name": "", "username": ""})
        rec["last"] = now
        rec["name"] = getattr(u, "full_name", "") or rec["name"]
        rec["username"] = getattr(u, "username", None) or rec["username"]

    # --- profil ---
    def profile(self, uid):
        return dict(self.profiles.get(uid, {}))

    def set_profile(self, uid, **kw):
        self.profiles.setdefault(uid, {}).update(kw)

    def clear_profile(self, uid):
        self.profiles.pop(uid, None)

    def save_from_form(self, uid, keys, data):
        """Formadagi javoblarni profilga saqlaydi. O'zgargan kalitlar ro'yxatini qaytaradi."""
        prof = self.profiles.setdefault(uid, {})
        changed = []
        for k in keys:
            v = (data.get(k) or "").strip()
            if v and v not in ("-", "—") and prof.get(k) != v:
                prof[k] = v
                changed.append(k)
        return changed

    # --- statistika ---
    def count(self, form):
        self.made[form] += 1

    def rate(self, form, up):
        self.rates[(form, "up" if up else "down")] += 1

    def stats_text(self):
        today = datetime.date.today()
        active = sum(1 for r in self.users.values() if r["last"].date() == today)
        lines = [f"📊 Statistika (bot ishga tushganidan: {self.started:%d.%m %H:%M})",
                 f"👥 Foydalanuvchilar: {len(self.users)} (bugun faol: {active})",
                 f"👤 Profil saqlaganlar: {len(self.profiles)}"]
        if self.made:
            lines.append("📄 Tayyorlangan: " + ", ".join(f"{k} {v}" for k, v in self.made.most_common()))
        forms = sorted({f for f, _ in self.rates})
        if forms:
            lines.append("⭐ Baholar: " + ", ".join(
                f"{f} 👍{self.rates[(f, 'up')]}/👎{self.rates[(f, 'down')]}" for f in forms))
        lines.append("\nEslatma: bu ma’lumotlar bot qayta ishga tushsa tozalanadi (v8 da bazaga o‘tadi).")
        return "\n".join(lines)


store = Store()
