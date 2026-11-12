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


async def _call(c, model, key, cfg, contents, system):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    think = True
    r = None
    for attempt in range(3):
        gc = dict(cfg)
        if think:
            gc["thinkingConfig"] = {"thinkingBudget": 0}  # tezroq va kamroq kvota
        body = {"contents": contents, "generationConfig": gc}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        r = await c.post(url, json=body, headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        if r.status_code == 400 and think:
            think = False
            continue
        if r.status_code in (429, 500, 503):
            await asyncio.sleep(4 * (attempt + 1))
            continue
        break
    return r


async def generate(prompt: str, json_mode: bool = False, max_tokens: int = 8192, key=None, system=None,
                   history=None, sem=None) -> str:
    global _good
    import httpx  # python-telegram-bot bilan birga o'rnatiladi

    key = key or os.getenv("GEMINI_API_KEY")
    if not key:
        raise AIError("no_key")
    cfg = {"temperature": 0.7, "maxOutputTokens": max_tokens}
    if json_mode:
        cfg["responseMimeType"] = "application/json"
    contents = [{"role": h["role"], "parts": [{"text": h["text"]}]} for h in (history or [])]
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    order = ([_good] if _good else []) + [m for m in MODELS if m != _good]
    r = None
    async with (sem or _sem):
        async with httpx.AsyncClient(timeout=240) as c:
            for model in order:
                r = await _call(c, model, key, cfg, contents, system)
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


CHAT_SYSTEM = """You are ClooerAI, a friendly and knowledgeable assistant for university students in Uzbekistan.
- Reply in the language the user writes in (default: Uzbek, Latin script).
- Be accurate, clear and well structured; use short paragraphs and simple lists. Keep answers under about 3000 characters unless the user asks for more.
- If you are not sure about a fact, say so; never invent sources, quotes, laws or statistics.
- For medical, legal or financial questions give general information and advise consulting a professional.
- Refuse requests that are harmful, illegal or sexual."""
_chat_sem = asyncio.Semaphore(4)


async def chat(history, text):
    """Suhbat: alohida kalit (GEMINI_CHAT_KEY) bilan, hujjat kvotasiga tegmaydi."""
    key = os.getenv("GEMINI_CHAT_KEY") or os.getenv("GEMINI_API_KEY")
    return await generate(text, max_tokens=3000, key=key, system=CHAT_SYSTEM, history=history, sem=_chat_sem)


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


TITLES = {
    "uz": dict(intro="Kirish", concl="Xulosa", refs="Foydalanilgan adabiyotlar ro‘yxati",
               lit="Adabiyotlar tahlili va metodologiya", res="Natijalar va muhokama"),
    "ru": dict(intro="Введение", concl="Заключение", refs="Список использованной литературы",
               lit="Обзор литературы и методология", res="Результаты и обсуждение"),
    "en": dict(intro="Introduction", concl="Conclusion", refs="References",
               lit="Literature review and methodology", res="Results and discussion"),
}


def _toks(words):
    return min(20000, int(words * 1.25 * 5) + 800)


async def make_refs(subject, topic, lang, n=10):
    """Adabiyotlar ro'yxati: O'zDSt 7.1 (GOST 7.1) bibliografik tavsif uslubida."""
    prompt = f"""List {n} references for an academic paper.
Language of the list: {LANG_NAME[lang]} (foreign-language sources may stay in their original language).
Subject: {subject}. Topic: {topic}.
Rules: cite ONLY real, well-known sources you are confident exist: the Constitution, laws and presidential decrees of Uzbekistan (only if relevant to the topic), standard textbooks, monographs. No URLs. Never invent authors, titles, publishers, years or page counts; if unsure about details, choose a different well-known source.
Order: legal acts first, then books and articles alphabetically by the author's surname.
Format every item as an O'zDSt 7.1 / GOST 7.1 bibliographic description, for example:
Karimov I.A. Yuksak ma'naviyat - yengilmas kuch. - Toshkent: Ma'naviyat, 2008. - 176 b.
Return ONLY JSON: {{"refs":["...","..."]}}"""
    data = parse_json(await generate(prompt, json_mode=True, max_tokens=3000))
    refs = []
    for r in data["refs"]:
        r = re.sub(r"^\s*\d+[.)]\s*", "", str(r)).strip()
        if r:
            refs.append(r)
    if not refs:
        raise AIError("empty")
    return refs


async def write_document(kind, subject, topic, lang, pages):
    """kind: mustaqil | referat | kurs | maqola. Bo'lim-bo'lim yozadi (uzunlik aniq chiqishi uchun)."""
    L, T = LANG_NAME[lang], TITLES[lang]
    refs = await make_refs(subject, topic, lang, 10 if pages <= 15 else 14 if pages <= 30 else 18)
    refs_txt = "\n".join(f"{i}. {r}" for i, r in enumerate(refs, 1))

    front = {"kurs": 5, "maqola": 1}.get(kind, 3)  # titul, reja, adabiyotlar sahifalari
    total = max(500 if kind == "maqola" else 600, int((pages - front) * 250))

    if kind == "maqola":
        plan = [(T["intro"], []), (T["lit"], []), (T["res"], []), (T["concl"], [])]
        shares = [0.2, 0.25, 0.35, 0.2]
        w_parts = [int(total * x) for x in shares]
        outline_txt = "; ".join(t for t, _ in plan)
    else:
        n_sec = 3 if kind == "kurs" else 3 if pages <= 8 else 4 if pages <= 12 else 5 if pages <= 16 else 6
        n_sub = 3 if kind == "kurs" else 2
        op = f"""You are an expert university teacher. Plan a {"course paper" if kind == "kurs" else "paper"}.
Language: {L}
Subject: {subject}
Topic: {topic}
Make an outline with exactly {n_sec} main sections; each has exactly {n_sub} subsection titles (short, specific).
Section titles are numbered like "1. ...", subsections like "1.1. ...". Titles in the target language.
Return ONLY JSON: {{"sections":[{{"title":"","subsections":["",""]}}]}}"""
        sections = parse_json(await generate(op, json_mode=True, max_tokens=4000))["sections"][:n_sec]
        plan = [(T["intro"], [])] + [(x["title"], x["subsections"]) for x in sections] + [(T["concl"], [])]
        w_intro, w_concl = int(total * 0.08), int(total * 0.07)
        w_sec = int((total - w_intro - w_concl) / len(sections))
        w_parts = [w_intro] + [w_sec] * len(sections) + [w_concl]
        outline_txt = "\n".join(f'{t}: ' + "; ".join(sb) for t, sb in plan)

    extra_by_pos = {
        0: ("Cover: relevance of the topic, aim and tasks, object and subject of the study, and the structure of the work."
            if kind in ("kurs", "referat", "mustaqil") else "Cover: relevance, aim and tasks of the article."),
        len(plan) - 1: "Summarize the main findings of all sections and give practical conclusions/recommendations.",
    }

    def head(title, words, what):
        return f"""You are an expert university teacher writing a part of an academic paper.
Language: {L}
Subject: {subject}
Topic: {topic}
Outline of the whole paper (for context only):
{outline_txt}

Reference list (the ONLY sources you may cite):
{refs_txt}

{what}
Length: AT LEAST {int(words * 1.25)} words of long, rich paragraphs (6-9 sentences each).
Style: formal academic. Support statements with in-text citations in square brackets using ONLY numbers from the reference list above, e.g. [2] or [3, 15-b]; 2-4 citations per part. Never invent statistics, quotes or sources.
Output: plain paragraphs separated by blank lines. No headings, no bold/italic markers, no tables, no bullet lists, no references list."""

    entries = []
    for pos, ((title, subs), words) in enumerate(zip(plan, w_parts)):
        entries.append(("s", f"# {title}"))
        extra = extra_by_pos.get(pos, "Cover definitions, background, mechanisms, concrete examples, comparisons and significance.")
        per_sub = subs and (kind == "kurs" or words > 900)
        if per_sub:
            per = max(150, words // len(subs))
            for sb in subs:
                entries.append(("s", f"## {sb}"))
                what = f'Write ONLY the body text of the subsection "{sb}" of the section "{title}". {extra}'
                entries.append(("j", generate(head(sb, per, what), max_tokens=_toks(per))))
        else:
            sub_txt = (" Use these subsections as lines starting with '## ', in this order, each followed by its paragraphs: "
                       + "; ".join(subs) + ".") if subs else ""
            what = f'Write ONLY the body text of the section "{title}". {extra}{sub_txt}'
            entries.append(("j", generate(head(title, words, what), max_tokens=_toks(words))))

    results = iter(await asyncio.gather(*[e[1] for e in entries if e[0] == "j"]))
    chunks = []
    for typ, val in entries:
        if typ == "s":
            chunks.append(val)
        else:
            body = next(results).strip()
            body = "\n".join(l for l in body.split("\n") if not l.strip().startswith("# "))
            chunks.append(body.strip())
    chunks.append("# " + T["refs"])
    chunks.append("\n".join(f"{i}. {r}" for i, r in enumerate(refs, 1)))
    return "\n\n".join(chunks)


async def make_insho(topic, lang, words, style):
    st = ("formal, academic-publicistic style" if style == "formal" else
          "free, expressive, creative style with personal reflection")
    prompt = f"""Write an essay (insho) in {LANG_NAME[lang]} on the topic: "{topic}".
Style: {st}. Length: about {words} words (not less than {int(words * 0.9)}).
Structure: introduction with a clear thesis, 2-4 body paragraphs with arguments and examples, conclusion.
Output: plain paragraphs separated by blank lines. No title, no headings, no bold markers, no lists."""
    return (await generate(prompt, max_tokens=_toks(words))).strip()


async def make_tezis(topic, field, lang):
    prompt = f"""Write conference theses (tezis) in {LANG_NAME[lang]}.
Topic: {topic}. Field: {field}.
Length: 350-450 words, 3-5 dense paragraphs: relevance, main idea/arguments, results/conclusion.
Cite sources in square brackets like [1], [2] using the numbering of the reference list you give at the end.
After the text, a line "# {TITLES[lang]['refs']}" and 3-5 numbered references (1. ...) in O'zDSt 7.1 / GOST 7.1 style.
Only real, well-known sources you are sure exist; never invent details. No bold markers, no lists in the body.
Output: paragraphs separated by blank lines, then the reference list."""
    return (await generate(prompt, max_tokens=4000)).strip()


async def make_annotations(topic, field, lang):
    prompt = f"""For a scientific article on the topic "{topic}" (field: {field}) write an annotation and keywords in THREE languages.
Each annotation: 40-60 words. Each keywords list: 5-7 words.
Return ONLY JSON: {{"uz":{{"annotation":"","keywords":""}},"ru":{{"annotation":"","keywords":""}},"en":{{"annotation":"","keywords":""}}}}
Uzbek must be in Latin script; keywords are comma-separated."""
    return parse_json(await generate(prompt, json_mode=True, max_tokens=3000))


async def make_keys(subject, topic, lang):
    prompt = f"""Write a case study (keys) for university students in {LANG_NAME[lang]}.
Subject: {subject}. Topic: {topic}.
Use these parts, each as a heading line starting with "# " (heading names in the target language):
1) Case description (a realistic situation with context, participants, numbers only if clearly illustrative; 250-350 words),
2) Problem statement,
3) Questions for discussion (6-8 questions, lines starting with "- "),
4) Guidance for analysis and possible solutions (150-250 words),
5) Conclusion (60-100 words).
Fictional participants/organizations must be clearly generic. No bold markers. Output only the text."""
    return (await generate(prompt, max_tokens=7000)).strip()


async def make_test(subject, topic, lang, n, level):
    lvl = {"easy": "easy", "mid": "medium", "hard": "hard"}.get(level, "medium")
    batches = []
    left, part = n, 1
    while left > 0:
        k = min(20, left)
        batches.append((k, part))
        left -= k
        part += 1

    async def one(k, part):
        prompt = f"""Create {k} multiple-choice test questions for university students.
Language: {LANG_NAME[lang]}. Subject: {subject}. Topic: {topic}. Difficulty: {lvl}.
This is part {part} of {len(batches)}: cover DIFFERENT subtopics than other parts.
Each question has exactly one correct answer and exactly 3 plausible wrong answers; all options similar in length; no "all of the above".
Return ONLY JSON: {{"questions":[{{"q":"","correct":"","wrong":["","",""]}}]}}"""
        d = parse_json(await generate(prompt, json_mode=True, max_tokens=9000))
        return d["questions"]

    res = await asyncio.gather(*[one(k, p) for k, p in batches])
    qs = []
    for part in res:
        for q in part:
            if q.get("q") and q.get("correct") and len(q.get("wrong", [])) >= 3:
                qs.append({"q": str(q["q"]).strip(), "correct": str(q["correct"]).strip(),
                           "wrong": [str(w).strip() for w in q["wrong"][:3]]})
    if not qs:
        raise AIError("empty")
    return qs[:n]


async def make_glossary(subject, topic, lang, n):
    prompt = f"""Create a glossary of exactly {n} key terms for university students.
Language: {LANG_NAME[lang]}. Subject: {subject}. Topic: {topic}.
Each definition: 1-2 clear sentences, accurate and standard. Terms must be distinct.
Return ONLY JSON: {{"terms":[{{"term":"","definition":""}}]}}"""
    d = parse_json(await generate(prompt, json_mode=True, max_tokens=9000))
    terms = [{"term": str(t["term"]).strip(), "definition": str(t["definition"]).strip()}
             for t in d["terms"] if t.get("term") and t.get("definition")]
    if not terms:
        raise AIError("empty")
    return terms


async def make_crossword_words(topic, lang, n):
    prompt = f"""Create words and clues for a crossword puzzle on the topic "{topic}".
Language: {LANG_NAME[lang]}. Give {n + 6} items.
Each answer is ONE word of 4-12 letters (letters only: no spaces, hyphens, digits or apostrophes), UPPERCASE.
Each clue is short (max 14 words), unambiguous, and does not contain the answer.
Return ONLY JSON: {{"items":[{{"word":"","clue":""}}]}}"""
    d = parse_json(await generate(prompt, json_mode=True, max_tokens=5000))
    items, seen = [], set()
    for it in d["items"]:
        w = re.sub(r"[^\w]", "", str(it.get("word", "")).upper().replace("_", ""))
        if 4 <= len(w) <= 12 and w not in seen and it.get("clue"):
            seen.add(w)
            items.append({"word": w, "clue": str(it["clue"]).strip()})
    if len(items) < 5:
        raise AIError("empty")
    return items
