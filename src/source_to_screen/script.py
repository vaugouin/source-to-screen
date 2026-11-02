"""The script pass: Claude writes the episode, beat by beat, from the reviewed comparison and outline,
the reviewer's decisions (review stop 1) and a few external sources, in three parts so each answer
stays well under the output cap. Same cached corpus as the comparison (novel, subtitles, ledger).

Output: work/<pair>/script/part-<k>.json and script.json (all beats), each beat with the speaker
(reader | viewer), the clean text, the spoken version with Gemini vocal tags, a delivery hint, the
ids that ground it and the visual to show. `check()` adds the script rules: no em dash, no unknown
id, no ten words copied from the novel, hype words, word counts and pace estimates.

The decisions of review stop 1 live in work/<pair>/script/decisions.md and the external sources in
work/<pair>/script/web.json (under work/: they paraphrase the works, never committed)."""
import json
import re

from . import compare, config

SCRIPT_RULES = """You are the head writer of a long-form, two-host, video podcast that compares a film with the
work it adapts. You write from evidence, never from memory: the CORPUS below holds the whole novel (paragraph
ids), the film's whole subtitle track (cue ids, master timecodes), the API ledger (api: ids), and the review
material follows it. The hosts are synthetic voices and say so at the end; they never pretend to be people.

The two hosts (stable personas of the series, no names, never on screen):
- THE READER (a woman): she has read the novel closely; she carries its story, its people, its chapters. Dry
  wit, precise, protective of the book but never blind to its faults.
- THE VIEWER (a man): he knows the film frame by frame and its production history; he carries the subtitles,
  the cast, the shoot, the reception. Warm, quick, enjoys a punchline, concedes when the text proves him wrong.
Each owns one work and reveals things the other did not know (real surprise, at the level of the material).

Hard rules:
1. Every fact line (track "fact") lists ids in `refs` that exist in the CORPUS or in the web ledger (web: ids).
   Performance lines (reactions, transitions, jokes) have `refs: []` and assert no fact. A line never says more
   than its refs: no added number, name, date or quotation.
2. The novel is retold, never read: no run of ten consecutive words from the novel anywhere. Verbatim novel text
   only for the three lines the film keeps (quotes_used of the outline), each under 15 words. Film lines may be
   quoted briefly (under 15 words) from their cue. Kubrick's letter (api:m935.wiki.themes-sexual-themes) may be
   quoted. Never read an id, a chapter number with a paragraph, or a timecode aloud; "in chapter five" is fine.
3. The audio must stand alone: a quarter of the audience only listens. Never "as you can see"; the line says
   what the picture shows.
4. Statements stay statements: "Kubrick wrote" is attested; "Kubrick wanted" is a reading the host voices as a
   reading ("I read that as..."). Inferences are marked as such in the dialogue.
5. Register (checked by a script): about 150 words per minute of speech; median turn about 20 words, telling
   turns 40 to 80 words, reactions 1 to 12 words, at least a quarter of turns short; generic backchannels
   ("Right.", "Exactly.", "Wow.") at most one per minute and never the same twice within three minutes: prefer
   content reactions (a guess, a question, an objection); banned words: amazing, groundbreaking, fascinating,
   mind-blowing, deep dive, totally, incredible, delve, tapestry, testament; at most one superlative per ten
   minutes; no em dash anywhere (use commas, colons, parentheses); adult syntax, varied vocabulary.
6. Dramaturgy: at least three real disagreements per half hour, each side with a sourced reason, at least one
   left unresolved and one ending in a partial concession; strong agreement only after a disagreement; 3 to 6
   laughs per ten minutes, at phrase ends, mostly after ordinary remarks; one running gag or ritual line set up
   in the first third and paid off twice; once, a small slip about a work corrected by the other host with the
   evidence, conceded with good humour; one or two short role-play beats (the hosts voice two characters, or
   the novelist and the screenwriter); each host criticises at least one choice of each version; analogies only
   from the works, the period or Kubrick's other films.
7. Gemini speech field: `speech` repeats `text` word for word and may add inline vocal tags in angle brackets
   (<laugh>, <chuckle>, <sigh>, <short pause>, <long pause>, <gasp>) and |backchannels| (a reaction of the OTHER
   host under the line, one to three words, at most one per line, 1 to 2 per minute overall). Omit `speech` when
   it would equal `text`. Never put a fact in `speech` that is not in `text`. Avoid "um" and "uh" (one per few
   minutes at most); prefer silences and self-corrections.
8. `delivery` is a short acting direction for that line (emotion, pace, emphasis), in English.
9. Output only one JSON object, no prose, no markdown fence.

Visuals (one per beat; "hold" keeps the previous picture). Change the picture every two to four beats; never
hold one picture for more than about 25 seconds of speech. About 70 % of screen time should show film stills,
the rest cards, posters, portraits. Types:
- {"type": "still", "cue": "en-sdh.0274", "shows": "Ripper at his desk, cigar, saying the line", "caption": "...",
   "quoted": true}  a frame of the film at the start of that cue. RULE: the frame must show exactly what the
   line is about: the character who speaks the quoted line, on screen while saying it. Pick the cue where that
   character is visible (not a reaction shot, not another set). `shows` says what must be visible, so the
   frame can be checked. For a moment with no dialogue, use "time": "h:mm:ss" instead of "cue" (the opening
   refuelling, the bomb ride, the explosions) and say what is visible. `caption`: for a quoted line, the line
   itself then the speaker, plus "(Red Alert, chapter N: nearly the same words)" when the novel has it; else a
   short descriptive caption. `quoted` true when the caption is a film line.
- {"type": "split", "left": {"cue" or "time", "shows"}, "right": {...}, "caption": "..."}  two film frames.
- {"type": "title_card", "works": ["novel"] or ["film"] or ["novel", "film"] or ["failsafe"], "caption": "..."}
- {"type": "portraits", "people": [{"name": exact name from the PEOPLE list, "caption": "..."}], "caption": "..."}
- {"type": "posters", "items": [keys from the POSTERS list], "caption": "..."}
- {"type": "quote_card", "text": "...", "attribution": "..."}  a quotation (film line, Kubrick's letter) or a
   novel paraphrase whose attribution says "Red Alert, chapter N (paraphrase)".
- {"type": "card", "title": "...", "lines": ["...", "..."], "source": "..."}  a fact card, a list, a chapter
   card at the start of each segment (title = segment title), a two-column comparison ("Novel: ..." / "Film:
   ..."). Short lines, at most six.
- {"type": "hold"}"""

PART_TASK = """Write PART {k} of 5 of the episode script: segments {segments} of the revised plan.
{previous}
Return one JSON object:
{{"part": {k},
 "beats": [{{"id": "b{k}001".., "seg": segment number, "voice": "reader|viewer", "track": "fact|performance",
   "text": "...", "speech": "..." (optional), "delivery": "...", "refs": [ids], "visual": {{...}},
   "pause_after_ms": 0 (use 600 to 1200 at the end of a segment)}}],
 "chapters": [{{"beat": first beat id of the segment, "title": segment title}}],
 "notes": [anything the producer must check: a still you are unsure of, a fact you softened]}}
Length: write the full dialogue of these segments at the minutes of the plan (about 150 words per minute of
speech). Do not summarise, do not skip: this is the final script. Think briefly: the material is already
analysed in the comparison and the outline; spend your effort on the dialogue itself."""

PARTS = {1: "1 to 3", 2: "4 and 5", 3: "6 to 8", 4: "9 to 11", 5: "12 to 14"}


def _block(slug: str) -> str:
    """Review material: decisions, web ledger, people and posters, comparison, outline."""
    d = config.work(slug, "review")
    data = config.work(slug, "script")
    m = config.load(config.work(slug, "facts") / "movie.json")
    people = [f"{c['PERSON_NAME']} ({c.get('CAST_CHARACTER') or c.get('CREW_JOB')})"
              for c in (m.get("cast") or [])[:20] + (m.get("crew") or []) if c.get("PROFILE_PATH")]
    web = config.load(data / "web.json")
    out = ["# REVIEW MATERIAL", "", (data / "decisions.md").read_text(encoding="utf-8"), "",
           "## Web ledger (web: ids, external sources read on 2026-11-02)"]
    out += [f"{e['id']} | {e['source']} | {e['claim']}" for e in web["entries"]]
    out += ["", "## PEOPLE with a portrait (use these exact names in portraits)", "; ".join(people), "",
            "## POSTERS (keys for posters)", "; ".join(f"{k}: {v['title']} ({v['year']})" for k, v in web["posters"].items()),
            "", "## Comparison (reviewed)", json.dumps(config.load(d / "compare.json"), ensure_ascii=False), "",
            "## Outline (reviewed; the revised plan in the decisions overrides it)",
            json.dumps(config.load(d / "outline.json"), ensure_ascii=False)]
    return "\n".join(out)


def ids_with_web(slug: str, ids: set[str]) -> set[str]:
    return ids | {e["id"] for e in config.load(config.work(slug, "script") / "web.json")["entries"]}


HYPE = re.compile(r"\b(amazing|groundbreaking|fascinating|mind-blowing|deep dive|totally|incredible|delve|tapestry|testament)\b", re.I)


def check(slug: str, obj: dict, ids: set[str]) -> dict:
    beats = obj["beats"]
    rep = compare.check(slug, {"beats": [{"text": b["text"], "speech": b.get("speech", ""), "refs": b.get("refs", []),
                                          "visual": b.get("visual", {})} for b in beats]}, ids)
    words = [len(b["text"].split()) for b in beats]
    rep.update(beats=len(beats), words=sum(words), minutes_at_150=round(sum(words) / 150, 1),
               reader_share=round(sum(w for w, b in zip(words, beats) if b["voice"] == "reader") / max(1, sum(words)), 2),
               short_turns=round(sum(w <= 12 for w in words) / max(1, len(words)), 2),
               median_turn=sorted(words)[len(words) // 2] if words else 0,
               em_dash=[b["id"] for b in beats if "—" in b["text"] + b.get("speech", "")],
               hype=[(b["id"], HYPE.search(b["text"])[0]) for b in beats if HYPE.search(b["text"])],
               fact_without_refs=[b["id"] for b in beats if b["track"] == "fact" and not b.get("refs")],
               speech_mismatch=[b["id"] for b in beats if b.get("speech") and
                                re.sub(r"<[^>]*>|\|[^|]*\||[^a-z0-9]", "", b["speech"].lower()) !=
                                re.sub(r"[^a-z0-9]", "", b["text"].lower())])
    return rep


def run(slug: str, parts: list[int] | None = None) -> dict:
    d = config.work(slug, "script")
    text, ids = compare.corpus(slug)
    ids = ids_with_web(slug, ids)
    extra = _block(slug)
    done = {}
    for k in parts or list(PARTS):
        prev = []
        for j in range(1, k):
            f = d / f"part-{j}.json"
            if f.exists():
                prev += [f"{b['voice']}: {b['text']}" for b in config.load(f)["beats"]]
        previous = ("Here is the script so far, for continuity (callbacks, running gag, no repetition):\n"
                    + "\n".join(prev) + "\n") if prev else ""
        raw, usage = compare.ask(text, PART_TASK.format(k=k, segments=PARTS[k], previous=previous),
                                 rules=SCRIPT_RULES, extra=extra, effort="medium", max_tokens=96000)
        (d / f"part-{k}.raw.txt").write_text(raw, encoding="utf-8")
        obj = compare.parse(raw)
        config.save(d / f"part-{k}.json", obj)
        rep = check(slug, obj, ids)
        config.save(d / f"part-{k}.check.json", dict(usage=usage, **rep))
        done[k] = dict(cost=usage["cost_usd"], beats=rep["beats"], words=rep["words"], unknown=len(rep["unknown"]),
                       copies=len(rep["copies"]), cache_read=usage["cache_read"])
        print(f"part {k}: {done[k]}", flush=True)
    merge(slug)
    return done


def merge(slug: str) -> dict:
    d = config.work(slug, "script")
    beats, chapters, notes = [], [], []
    for k in PARTS:
        f = d / f"part-{k}.json"
        if f.exists():
            o = config.load(f)
            beats += o["beats"]
            chapters += o.get("chapters", [])
            notes += o.get("notes", [])
    obj = dict(beats=beats, chapters=chapters, notes=notes)
    config.save(d / "script.json", obj)
    _, ids = compare.corpus(slug)
    rep = check(slug, obj, ids_with_web(slug, ids))
    config.save(d / "script.check.json", rep)
    return rep


JUDGE_TASK = """You are now the fact-checker of the script below (the producer's last gate before synthesis). For EVERY
beat, check the spoken text against the ids it cites (refs), the CORPUS and the web ledger, and against the
reviewer's decisions. Flag a beat when: it states something its refs do not support (an added number, name, date,
quotation or event); it contradicts the novel's text or a subtitle; it presents an inference as a fact; it breaks a
decision (torture motive, Laputa/Swift, measures talk, the ending footnote placed early, wrong crew count, a novel
rating); a quoted film line is not what the cue says; a performance beat asserts a fact. Also flag a still whose
`shows` cannot be what the cited cue's moment shows (wrong speaker, wrong setting from the cue's setting label).
Do not flag style. Be strict on facts, silent on taste.

SCRIPT:
{script}

Return one JSON object: {{"issues": [{{"id": beat id, "kind": "unsupported|contradicted|inference|decision|quote|
performance-fact|still", "problem": "...", "fix_text": the corrected spoken text, same voice and length, or null to
delete the beat, "fix_refs": [ids] or null}}], "summary": "..."}}"""


def judge(slug: str) -> dict:
    d = config.work(slug, "script")
    text, ids = compare.corpus(slug)
    sc = config.load(d / "script.json")
    lines = [json.dumps(dict(id=b["id"], voice=b["voice"], track=b["track"], text=b["text"], refs=b.get("refs", []),
                             visual={k: v for k, v in (b.get("visual") or {}).items() if k in ("type", "cue", "time", "shows", "caption", "text")}),
                        ensure_ascii=False) for b in sc["beats"]]
    raw, usage = compare.ask(text, JUDGE_TASK.format(script="\n".join(lines)), rules=SCRIPT_RULES, extra=_block(slug),
                             effort="medium", max_tokens=96000)
    (d / "judge.raw.txt").write_text(raw, encoding="utf-8")
    obj = compare.parse(raw)
    config.save(d / "judge.json", dict(usage=usage, **obj))
    return dict(cost=usage["cost_usd"], issues=len(obj.get("issues", [])))
