"""Slaydlar uchun mavzuga mos rasmlar: Pexels / Pixabay (kalit bo'lsa), aks holda Wikimedia Commons."""
import asyncio
import io
import os

UA = {"User-Agent": "ClooerAIBot/1.0 (https://t.me/clooerai; student slides helper)"}


def prepare(data: bytes, ratio: float, max_w: int = 1000):
    """Rasmni kerakli nisbatga kesadi va siqadi (JPEG)."""
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size
    if w < 500 or h < 300:
        return None
    if w / h > ratio:  # juda keng -> yon tomondan kesamiz
        nw = int(h * ratio)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:  # juda baland -> yuqori/pastdan kesamiz
        nh = int(w / ratio)
        top = max(0, (h - nh) // 4)
        im = im.crop((0, top, w, top + nh))
    if im.width > max_w:
        im = im.resize((max_w, int(max_w / ratio)))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=82)
    return out.getvalue()


async def _pexels(c, query, key):
    r = await c.get("https://api.pexels.com/v1/search",
                    params={"query": query, "per_page": 5, "orientation": "landscape"},
                    headers={"Authorization": key})
    if r.status_code != 200:
        return None
    for p in r.json().get("photos", []):
        url = p["src"].get("large") or p["src"].get("medium")
        if url:
            d = await c.get(url)
            if d.status_code == 200:
                return d.content
    return None


async def _pixabay(c, query, key):
    r = await c.get("https://pixabay.com/api/", params={
        "key": key, "q": query, "image_type": "photo", "orientation": "horizontal",
        "per_page": 5, "safesearch": "true", "min_width": 800})
    if r.status_code != 200:
        return None
    for p in r.json().get("hits", []):
        url = p.get("largeImageURL") or p.get("webformatURL")
        if url:
            d = await c.get(url)
            if d.status_code == 200:
                return d.content
    return None


async def _wikimedia(c, query):
    r = await c.get("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 8,
        "prop": "imageinfo", "iiprop": "url|mime|size", "iiurlwidth": 1000,
    })
    if r.status_code != 200:
        return None
    pages = (r.json().get("query") or {}).get("pages") or {}
    for p in sorted(pages.values(), key=lambda x: x.get("index", 99)):
        info = (p.get("imageinfo") or [{}])[0]
        if info.get("mime") != "image/jpeg":
            continue
        if info.get("width", 0) < 700 or info.get("height", 0) < 450:
            continue
        url = info.get("thumburl") or info.get("url")
        if url:
            d = await c.get(url)
            if d.status_code == 200:
                return d.content
    return None


async def fetch_all(queries, ratio):
    """queries: ro'yxat (str yoki ''). Natija: bir xil uzunlikdagi ro'yxat (bytes yoki None)."""
    import httpx

    key = os.getenv("PEXELS_API_KEY")
    pix = os.getenv("PIXABAY_API_KEY")
    sem = asyncio.Semaphore(4)

    async def one(c, q):
        if not q:
            return None
        async with sem:
            try:
                raw = None
                if key:
                    raw = await _pexels(c, q, key)
                if raw is None and pix:
                    raw = await _pixabay(c, q, pix)
                if raw is None:
                    raw = await _wikimedia(c, q)
                return prepare(raw, ratio) if raw else None
            except Exception:
                return None

    async with httpx.AsyncClient(timeout=15, headers=UA, follow_redirects=True) as c:
        return await asyncio.gather(*[one(c, q) for q in queries])


# ---------------- Rasm -> PDF ----------------
def shrink(raw: bytes):
    """Yuborilgan rasmni (foto yoki fayl) yengil JPEG'ga aylantiradi. Ochilmasa None."""
    from PIL import Image, ImageOps

    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    except Exception:
        return None
    im.thumbnail((2000, 2000))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=88)
    return out.getvalue()


def make_pdf(jpegs, out_path):
    """Har bir rasm — alohida A4 sahifa (yo'nalishi rasmga qarab tanlanadi)."""
    from PIL import Image, ImageOps

    A4 = (1075, 1520)  # ~130 dpi
    pages = []
    for b in jpegs:
        im = Image.open(io.BytesIO(b)).convert("RGB")
        size = A4 if im.height >= im.width else (A4[1], A4[0])
        im = ImageOps.contain(im, (size[0] - 60, size[1] - 60))
        page = Image.new("RGB", size, "white")
        page.paste(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
        pages.append(page)
    pages[0].save(out_path, "PDF", resolution=130.0, save_all=True, append_images=pages[1:])
    return out_path
