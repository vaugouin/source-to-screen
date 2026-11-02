"""The comparison pass and the outline pass: Claude reads the whole novel (paragraph ids), the
whole subtitle track (cue ids, master timecodes, setting of each cue from the frames), the
alignment measures and the API ledger, and writes the review material of review stop 1:
differences, characters, coverage, inventions, quotes, then a timed outline.

Grounding contract (study §6): every row cites ids that exist in the corpus; `check()` refuses
unknown ids and flags any run of ten words or more copied from the novel (the episode retells,
it does not quote, apart from a few short lines the film itself keeps).

One cached system prefix (rules + corpus, about 110k tokens) serves both passes. Model:
claude-opus-5-5 with adaptive thinking; the key is ANTHROPIC_API_KEY, read from the environment
or from the .env named by S2S_ANTHROPIC_ENV (default ~/Code/fastapi-text2sql/.env), never printed."""
import json
import os
import re
from pathlib import Path

from . import config, places

MODEL = "claude-opus-5-5"
ENV_FILE = Path(os.environ.get("S2S_ANTHROPIC_ENV", Path.home() / "Code" / "fastapi-text2sql" / ".env"))
ID = re.compile(r"^(ch\d\d\.p\d{3}|ch\d\d|en-sdh\.\d{4}|api:[\w.\-]+|web:[\w.\-]+|measure:[\w.\-/ ']+)$")


def _key() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*ANTHROPIC_API_KEY\s*=\s*(.*)", line)
        if m:
            return m[1].strip().strip('"')
    raise SystemExit("ANTHROPIC_API_KEY not found")


def hms(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


# ---------------------------------------------------------------- corpus

def corpus(slug: str) -> tuple[str, set[str]]:
    """The cached block: novel, subtitles, measures, ledger. Returns the text and the set of valid ids."""
    p = config.pair(slug)
    src = config.load(config.work(slug, "text") / "source.json")
    cues = config.load(config.work(slug, "subs") / "en-sdh.json")["cues"]
    al = config.load(config.work(slug, "align") / "alignment.json")
    pl_file = config.work(slug, "places") / "places.json"
    pl = config.load(pl_file) if pl_file.exists() else None
    led = config.load(config.work(slug, "facts") / "ledger-api.json")["entries"]
    ids: set[str] = set()

    out = [f"# CORPUS for the pair '{slug}'\n",
           f"Source work: {p['source_title']} by {p['source_author']} ({p['source_form']}). Film: {p['title']}.\n"]

    out.append("\n## A. The novel, every paragraph with its id (edition: Philippe's epub)\n")
    for ch in src["chapters"]:
        ids.add(ch["id"])
        out.append(f"\n### {ch['id']} | {ch['title']} | setting: {ch['place']}\n")
        for para in ch["paragraphs"]:
            ids.add(para["id"])
            out.append(f"{para['id']} | {para['text']}")

    out.append("\n\n## B. The film's subtitles (English SDH, master copy timeline), one cue per line\n"
               "Format: cue id | start time | setting read from the frames | text (speaker names and sound cues as in the SDH track)\n")
    for c in cues:
        if "rarbg" in c["text"].lower():
            continue
        ids.add(c["id"])
        where = places.place_at(pl, c["start"], c["end"] + 0.01) if pl else "?"
        out.append(f"{c['id']} | {hms(c['start'])} | {where} | {c['raw'].replace(chr(10), ' ')}")

    out.append("\n\n## C. Measures from source-to-screen (ids start with measure:)\n")
    out.append("Coverage per chapter: share of the chapter's ~120-word windows matched by film dialogue, "
               "'kept' on a monotone path in the novel's order, 'echoed' in any order. Similarity of meaning, "
               "not of words; a low share can still hide a retold event.\n")
    for c in al["coverage"]:
        mid = f"measure:coverage.{c['chapter']}"
        ids.add(mid)
        out.append(f"{mid} | {c['chapter']} | {c['place']} | {c['words']} words | kept {c['share']:.0%} | echoed {c['echo_share']:.0%}")
    out.append("\nMonotone path (film block -> novel window, cosine similarity):")
    for k, step in enumerate(al["path"]):
        b, w = al["blocks"][step["block"]], al["windows"][step["window"]]
        mid = f"measure:path.{k:03d}"
        ids.add(mid)
        out.append(f"{mid} | film {hms(b['start'])}-{hms(b['end'])} ({b['cues'][0]}..{b['cues'][-1]}) -> {w['id']} | sim {step['sim']}")
    out.append("\nFuzzy dialogue anchors (string similarity, may include false positives on short common phrases: judge them):")
    for k, a in enumerate(al["anchors"]):
        mid = f"measure:anchor.{k}"
        ids.add(mid)
        out.append(f"{mid} | {a['cue']} {hms(a['start'])} film: \"{a['film']}\" | {a['source']} novel fragment: \"{a['source_text']}\" | score {a['score']}")
    if pl:
        out.append("\nSettings read from the frames (one label per second, CLIP with exemplars, 24/24 correct on a check sample):")
        tot = {}
        for x in pl["seconds"]:
            tot[x["place"]] = tot.get(x["place"], 0) + 1
        words = {}
        for ch in src["chapters"]:
            words[ch["place"]] = words.get(ch["place"], 0) + sum(pp["words"] for pp in ch["paragraphs"])
        allw = sum(words.values())
        for place in sorted(set(tot) | set(words)):
            mid = f"measure:settings.{place.replace(' ', '_').replace('/', '-')}"
            ids.add(mid)
            out.append(f"{mid} | {place} | novel {words.get(place, 0)} words ({words.get(place, 0) / allw:.0%}) | "
                       f"film {tot.get(place, 0) / 60:.1f} min ({tot.get(place, 0) / len(pl['seconds']):.0%})")
        out.append("\nSequence of settings in the film:")
        prev, start = None, 0
        for x in pl["seconds"] + [dict(t=1e9, place=None)]:
            if x["place"] != prev:
                if prev and x["t"] - start > 20:
                    out.append(f"  {hms(start)}-{hms(x['t'])} {prev}")
                prev, start = x["place"], x["t"]

    out.append("\n\n## D. Ledger from the fastapi-text2sql API (ids start with api:)\n")
    for e in led:
        ids.add(e["id"])
        out.append(f"{e['id']} | {e['claim']}")
    return "\n".join(out), ids


RULES = """You are the comparison analyst of a two-host podcast that compares a film with the work it adapts.
One host is the reader (knows the novel), the other the viewer (knows the film). Your work is the evidence
layer, reviewed by a human before any script is written. Method: McFarlane's cardinal functions and
catalysers, Hutcheon's telling to showing, a taxonomy of difference types (retention, omission, addition,
compression, expansion, merging, splitting, reordering, displacement, substitution, character
transformation, promotion/demotion, focalisation shift, interiority externalised, genre/tone shift,
ending alteration, thematic revision, dialogue verbatim/paraphrase/invention, medium-specific invention,
censorship-driven change, industrial change). Explanations are one of: medium, context, intention
(only when a statement in the ledger supports it), or open (no support: say so, it becomes a debate).

Hard rules:
1. Every claim cites ids that appear in the CORPUS: novel paragraph ids (ch08.p053), chapter ids (ch08),
   cue ids (en-sdh.0269), api ids (api:m935.wiki.production-ending), measure ids (measure:coverage.ch05).
   Never invent an id. Prefer a paragraph or a cue over a chapter id.
2. Do not copy the novel: paraphrase. Never reproduce ten or more consecutive words of the novel, except in
   the `quotes` list, where only lines the film keeps almost word for word are allowed, each under 15 words.
3. Film lines may be quoted briefly (under 15 words) with their cue id and time.
4. Do not judge fidelity as a virtue. Describe, explain, then say what each change does to the meaning.
5. Separate what the sources say (attested) from what you read into them (inferred). Mark each row.
6. Times are on the master copy's timeline, h:mm:ss, taken from the cue lines.
7. IMDb ratings never apply to the novel.
8. Output only one JSON object, no prose before or after, no markdown fence."""

COMPARE_TASK = """Write the comparison as one JSON object with these keys:

"relation": {"label": Wagner/Andrew/Leitch label with one-line reason, "mode": "telling -> showing" note,
  "thesis": one "whereas" sentence, "evidence": [ids]}
"cardinal_functions": the 10 to 16 hinges of the novel's plot in order; each {"n", "novel": paraphrase,
  "novel_refs": [paragraph ids], "film": "present|altered|moved|absent", "film_note", "film_refs": [cue ids],
  "film_time": "h:mm:ss" or null, "confidence": "attested|inferred"}
"differences": 15 to 25 rows, the most telling first; each {"id": "D01".., "lens": one of story, quantity,
  characters, point of view, space and time, genre and tone, ending, theme, dialogue, style, production,
  reception, "label": taxonomy label, "novel": paraphrase, "film": description, "novel_refs", "film_refs",
  "film_time", "explanation_kind": "medium|context|intention|open", "explanation", "effect": what it does to
  the meaning, "evidence": [api or measure ids], "confidence", "debate": a question the two hosts could
  disagree on, or null}
"characters": every named character of either work who matters; each {"novel_name", "film_name",
  "status": "kept|renamed|transformed|merged|split|added|cut", "novel_role", "film_role", "actor" (from the
  ledger cast, or null), "novel_refs", "film_refs", "evidence", "note"}
"coverage": one row per novel chapter; each {"chapter", "setting", "novel_summary": one or two sentences,
  "on_screen": "kept|compressed|changed|merged|cut", "film_span": "h:mm:ss-h:mm:ss" or null, "film_refs",
  "evidence": [measure ids and refs], "note"}
"inventions": film material with no counterpart in the novel; each {"what", "film_span", "film_refs",
  "evidence", "explanation_kind", "explanation"}
"quotes": lines the film keeps almost verbatim from the novel; check every fuzzy anchor and search for others
  yourself; each {"cue", "time", "film_line", "novel_ref", "verdict": "verbatim|near|false_anchor", "note"};
  false anchors stay in the list with verdict false_anchor so the tool can learn from them.
"settings": what the measure:settings rows mean, 3 to 5 sentences, with ids.
"conflicts": places where sources disagree (ledger against text, film plot summary against the cues).
"data_gaps": errors or gaps you noticed in the ledger (wrong links, missing people, odd fields)."""

OUTLINE_TASK = """Here is the comparison you wrote earlier for this pair, already reviewed by the checker:

{comparison}

Now write the outline of a long-form two-host episode (no length cap, but no padding: every minute must
carry a fact, a scene or a debate; aim at 45 to 60 minutes). Plan of reference: 1 cold open, 2 framing and
thesis and spoiler promise, 3 the source in its world, 4 the road to the screen, 5 shape of the adaptation
(measures), 6 core lenses (three to five), 7 reception, 8 verdict and rituals ("who won the adaptation",
"best line in each version", "the scene the film should have kept"), 9 outro. The reader host is a woman,
the viewer host a man; neither is on screen. The episode retells the novel's story, it does not read it;
it may use two or three of the verbatim lines from `quotes` (verdict verbatim or near), each shown as a still
of the film at that time with the line as caption and the chapter of the novel.

Return one JSON object:
{"title", "thesis", "minutes_total",
 "segments": [{"n", "title", "minutes", "lead": "reader|viewer|both", "goal",
   "beats": [{"who": "reader|viewer|both", "beat": one or two sentences of content (not dialogue),
     "evidence": [ids], "visual": {"kind": one of still, quote-card, compare-cards, fact-card, timeline,
       coverage-map, alignment-curve, character-ledger, settings-bars, chain, stat-strip, portraits, poster,
       book-cover, map, verdict, "ref": a film time span "h:mm:ss-h:mm:ss" for stills, else what to show}}],
   "debate": the disagreement of the segment or null, "rehook": the question that leads into the next one}],
 "quotes_used": [cue ids],
 "stills": [{"name": slug, "start": "h:mm:ss", "end": "h:mm:ss", "why"}],
 "open_points": things the human reviewer must decide}"""


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=_key(), max_retries=3)


def ask(system_text: str, task: str, effort: str = "high", rules: str = RULES, extra: str | None = None,
        max_tokens: int = 64000) -> tuple[str, dict]:
    """`rules` then the corpus (cached), then `extra` (cached too: shared by several calls of one pass)."""
    client = _client()
    system = [{"type": "text", "text": rules},
              {"type": "text", "text": system_text, "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
    if extra:
        system.append({"type": "text", "text": extra, "cache_control": {"type": "ephemeral", "ttl": "1h"}})
    kwargs = dict(
        model=MODEL, max_tokens=max_tokens,
        thinking={"type": "adaptive"}, output_config={"effort": effort},
        system=system,
        messages=[{"role": "user", "content": task}],
    )
    with client.messages.stream(**kwargs) as stream:
        msg = stream.get_final_message()
    text = "".join(b.text for b in msg.content if b.type == "text")
    # save first: a crash below must not lose a paid answer
    (config.WORK / "last-answer.json").write_text(msg.model_dump_json(), encoding="utf-8")
    if msg.stop_reason == "max_tokens":
        raise SystemExit(f"answer cut at max_tokens ({u_out(msg)} output tokens): saved in work/last-answer.json")
    if msg.stop_reason == "refusal":
        raise SystemExit(f"refusal: {msg.stop_details}")
    u = msg.usage
    usage = dict(input=u.input_tokens, cache_write=u.cache_creation_input_tokens or 0,
                 cache_read=u.cache_read_input_tokens or 0, output=u.output_tokens, stop=msg.stop_reason,
                 request_id=getattr(msg, "id", None))
    # Opus 5.5 list prices: input $4, output $20, 1h cache write $8, cache read $0.20 per MTok
    usage["cost_usd"] = round(u.input_tokens * 4e-6 + usage["cache_write"] * 8e-6 + usage["cache_read"] * 0.2e-6
                              + u.output_tokens * 20e-6, 3)
    return text, usage


def u_out(msg) -> str:
    d = getattr(msg.usage, "output_tokens_details", None)
    return f"{msg.usage.output_tokens}, thinking {getattr(d, 'thinking_tokens', '?')}"


def parse(text: str) -> dict:
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    return json.loads(s[s.find("{"): s.rfind("}") + 1])


# ---------------------------------------------------------------- checker

def _walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, o


def check(slug: str, obj: dict, ids: set[str]) -> dict:
    """Unknown ids, and copies of ten consecutive words of the novel outside `quotes`."""
    src = config.load(config.work(slug, "text") / "source.json")
    norm = lambda s: re.findall(r"[a-z0-9']+", s.lower().replace("’", "'"))
    grams = set()
    for ch in src["chapters"]:
        for para in ch["paragraphs"]:
            w = norm(para["text"])
            grams.update(" ".join(w[i:i + 10]) for i in range(len(w) - 9))
    unknown, copies, cited = [], [], 0
    for path, v in _walk(obj):
        if not isinstance(v, str):
            continue
        if re.search(r"(refs|evidence|cue|novel_ref|quotes_used)(\[\d+\])?$", path):
            for token in re.split(r"[,\s]+", v.strip()):
                if not token:
                    continue
                cited += 1
                if not ID.match(token) or token not in ids:
                    unknown.append((path, token))
        elif ".quotes" not in path:
            w = norm(v)
            for i in range(len(w) - 9):
                if " ".join(w[i:i + 10]) in grams:
                    copies.append((path, " ".join(w[i:i + 10])))
                    break
    return dict(cited=cited, unknown=unknown, copies=copies)


# ---------------------------------------------------------------- run

def run(slug: str, step: str) -> dict:
    d = config.work(slug, "review")
    text, ids = corpus(slug)
    (d / "corpus.txt").write_text(text, encoding="utf-8")
    if step == "corpus":
        return dict(chars=len(text), ids=len(ids))
    if step == "compare":
        raw, usage = ask(text, COMPARE_TASK)
        (d / "compare.raw.txt").write_text(raw, encoding="utf-8")
        obj = parse(raw)
        report = check(slug, obj, ids)
        config.save(d / "compare.json", obj)
        config.save(d / "compare.check.json", dict(usage=usage, **report))
        return dict(usage=usage, cited=report["cited"], unknown=len(report["unknown"]), copies=len(report["copies"]))
    if step == "outline":
        comp = config.load(d / "compare.json")
        raw, usage = ask(text, OUTLINE_TASK.replace("{comparison}", json.dumps(comp, ensure_ascii=False)))
        (d / "outline.raw.txt").write_text(raw, encoding="utf-8")
        obj = parse(raw)
        report = check(slug, obj, ids)
        config.save(d / "outline.json", obj)
        config.save(d / "outline.check.json", dict(usage=usage, **report))
        return dict(usage=usage, cited=report["cited"], unknown=len(report["unknown"]), copies=len(report["copies"]))
    raise SystemExit(f"unknown step {step}")
