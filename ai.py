"""Gemini (Google AI Studio, bepul daraja) bilan ishlash."""
import asyncio
import json
import os
import re

# Google modellarni tez almashtirib turadi: 404 bo'lsa keyingisiga o'tadi.
MODELS = [m for m in (os.getenv("GEMINI_MODEL"), "gemini-3.1-flash-lite", "gemini-3.8-flash",
                      "gemini-3.5-flash-lite") if m]
_good = None  # oxirgi ishlagan model
_sem = asyncio.Semaphore(3)  # bir vaqtda ko'pi bilan 3 ta so'rov


class AIError(Exception):
    pass


async def _call(c, model, key, cfg, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    think = True
    r = None
    for attempt in range(3):
        gc = dict(cfg)
        if think:
            gc["thinkingConfig"] = {"thinkingBudget": 0}  # tezroq va kamroq kvota
        body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gc}
        r = await c.post(url, json=body, headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        if r.status_code == 400 and think:
            think = False
            continue
        if r.status_code in (429, 500, 503):
            await asyncio.sleep(4 * (attempt + 1))
            continue
        break
    return r


async def generate(prompt: str, json_mode: bool = False, max_tokens: int = 8192) -> str:
    global _good
    import httpx  # python-telegram-bot bilan birga o'rnatiladi

    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise AIError("no_key")
    cfg = {"temperature": 0.7, "maxOutputTokens": max_tokens}
    if json_mode:
        cfg["responseMimeType"] = "application/json"
    order = ([_good] if _good else []) + [m for m in MODELS if m != _good]
    r = None
    async with _sem:
        async with httpx.AsyncClient(timeout=240) as c:
            for model in order:
                r = await _call(c, model, key, cfg, prompt)
                if r.status_code == 404:  # model topilmadi -> keyingisi
                    continue
                if r.status_code == 200:
                    _good = model
                break
    if r.status_code == 429:
        raise AIError("busy")
    if r.status_code != 200:
        raise AIError(f"http {r.status_code}: {r.text[:300]}")
    try:
        parts = r.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
    except Exception:
        raise AIError("empty")
    if not text.strip():
        raise AIError("empty")
    return text


def parse_json(text: str):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    return json.loads(t)


LANG_NAME = {"uz": "Uzbek (Latin script, correct modern orthography)", "ru": "Russian", "en": "English"}


async def make_slides(topic, subject, lang, k):
    prompt = f"""You are an experienced university professor preparing a presentation that must impress teachers and classmates.
Language of ALL text: {LANG_NAME[lang]}
Subject: {subject}
Topic: {topic}
Create exactly {k} content slides (NO title slide, NO agenda slide, NO thank-you slide: they are added automatically). The LAST slide must be the conclusion.
Rules:
- Slide title: at most 7 words.
- 4 or 5 bullets per slide; each bullet is ONE complete, informative sentence of 10-18 words with concrete content (terms, dates, names, causes, examples). Use only well-established facts; never invent statistics, quotes or sources.
- key_point: one memorable takeaway sentence, at most 14 words.
- image_query: for about half of the slides give 2-4 ENGLISH words naming something concrete and photographable that fits the slide (e.g. "Registan Samarkand", "solar panels field"); otherwise an empty string. Never ask for images of real private persons. Conclusion slide: empty.
- notes: 2-3 sentences the presenter can say aloud for this slide.
- Logical flow: background, main parts, examples/significance, conclusion. Do not repeat content between slides.
Return ONLY JSON: {{"slides":[{{"title":"","bullets":[""],"key_point":"","image_query":"","notes":""}}]}}"""
    text = await generate(prompt, json_mode=True, max_tokens=24000)
    data = parse_json(text)
    slides = []
    for s in data["slides"]:
        title = str(s.get("title", "")).strip()
        bullets = [str(b).strip() for b in s.get("bullets", []) if str(b).strip()][:5]
        if title and bullets:
            slides.append({
                "title": title,
                "bullets": bullets,
                "key_point": str(s.get("key_point", "")).strip(),
                "image_query": str(s.get("image_query", "")).strip(),
                "notes": str(s.get("notes", "")).strip(),
            })
    if not slides:
        raise AIError("empty")
    return slides


async def make_paper(subject, topic, lang, pages):
    words = max(600, (pages - 3) * 230)
    prompt = f"""You are an expert university teacher. Write an independent study paper (mustaqil ish).
Language: {LANG_NAME[lang]}
Subject: {subject}
Topic: {topic}
Target length: about {words} words of body text (excluding the reference list).
Structure: Introduction, 3 or 4 main sections (each with 1-3 subsections), Conclusion, List of references.
Strict output format (no other text, no commentary):
- Section headings on their own line starting with "# " (e.g. "# 1. ...").
- Subsection headings on their own line starting with "## ".
- Body paragraphs as plain text separated by blank lines; each paragraph 4-8 sentences.
- Lists only as lines starting with "- ".
- No bold/italic markers, no tables, no links.
- The references section: 8-10 numbered lines ("1. ...") citing only well-known real textbooks, laws or standard sources you are confident exist; no URLs, no invented details.
Do not invent statistics or quotes."""
    return await generate(prompt, max_tokens=32000)
