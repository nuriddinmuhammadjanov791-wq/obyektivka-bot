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
    """Uzun ishni bo'limlarga bo'lib yozadi (bitta so'rovda model qisqa yozib qo'yadi)."""
    total = max(600, (pages - 3) * 250)
    n_sec = 3 if pages <= 8 else 4 if pages <= 12 else 5 if pages <= 16 else 6
    L = LANG_NAME[lang]

    outline_prompt = f"""You are an expert university teacher. Plan an independent study paper.
Language: {L}
Subject: {subject}
Topic: {topic}
Make an outline with exactly {n_sec} main sections; each main section has 2 or 3 subsection titles (short, specific).
Titles must be in the target language. Section titles start with numbers like "1. ...", subsections like "1.1 ...".
Return ONLY JSON: {{"intro_title":"","sections":[{{"title":"","subsections":["",""]}}],"conclusion_title":"","references_title":""}}"""
    plan = parse_json(await generate(outline_prompt, json_mode=True, max_tokens=4000))
    sections = plan["sections"][:n_sec]
    outline_txt = "\n".join(
        [plan["intro_title"]] + [f'{x["title"]}: ' + "; ".join(x["subsections"]) for x in sections]
        + [plan["conclusion_title"]])

    w_intro, w_concl = int(total * 0.08), int(total * 0.07)
    w_sec = int((total - w_intro - w_concl) / len(sections))

    def part_prompt(kind, title, subs, words):
        extra = {
            "intro": "Cover: relevance of the topic, aim, tasks, object and subject, and the structure of the paper.",
            "main": "Cover definitions, background/history, mechanisms, concrete examples, comparisons and significance.",
            "concl": "Summarize the main findings of all sections and give practical conclusions/recommendations.",
        }[kind]
        sub_txt = ("Subsections (use each as a '## ' heading, in this order): " + "; ".join(subs)) if subs else \
            "No subsection headings."
        return f"""You are an expert university teacher writing ONE part of an independent study paper.
Language: {L}
Subject: {subject}
Topic: {topic}
Full outline (for context, do not write other parts):
{outline_txt}

Write ONLY this part: "{title}".
{extra}
{sub_txt}
Length: AT LEAST {int(words * 1.25)} words. Write long, rich paragraphs (6-9 sentences each).
Format strictly: first line "# {title}", then subsection headings as lines starting with "## ", then plain paragraphs separated by blank lines.
No bold/italic markers, no tables, no links, no bullet lists, no references. Never invent statistics, quotes or sources."""

    def toks(w):
        return min(20000, int(w * 1.25 * 5) + 800)

    jobs = [generate(part_prompt("intro", plan["intro_title"], [], w_intro), max_tokens=toks(w_intro))]
    for x in sections:
        jobs.append(generate(part_prompt("main", x["title"], x["subsections"], w_sec), max_tokens=toks(w_sec)))
    jobs.append(generate(part_prompt("concl", plan["conclusion_title"], [], w_concl), max_tokens=toks(w_concl)))
    refs_prompt = f"""List 8-10 references for an independent study paper.
Language: {L}. Subject: {subject}. Topic: {topic}.
Cite only well-known real textbooks, laws or standard sources you are confident exist; no URLs, no invented details.
Format strictly: first line "# {plan["references_title"]}", then numbered lines "1. ...", one per line."""
    jobs.append(generate(refs_prompt, max_tokens=2000))
    parts = await asyncio.gather(*jobs)
    return "\n\n".join(p.strip() for p in parts)
