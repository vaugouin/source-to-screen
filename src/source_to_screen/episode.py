"""From the script (work/<pair>/script/script.json) to a voice-agent cinema scenario (contract:
~/Code/voice-agent/cinema/README.md), written to work/<pair>/episode/<pair>.json, never committed: it
retells the works. voice-agent builds it (`uv run tools/build-cinema-assets.py <path>`) into its own
cinema/assets/<slug>/, which it does not commit either.

Mapping:
- reader -> Gemini Laomedeia (the woman of the series), viewer -> Gemini Algenib (the man);
- a still at a cue -> a frame of the light SDR copy (same timeline as the master, -0.020 s, measured by
  `offsets`), taken at the sharpest moment INSIDE the cue, so the speaker of the line is on screen; a
  still at a time -> the sharpest frame in the next second and a half;
- people by name -> TMDb person ids of the film's cast and crew (API sheet); posters by key -> web.json;
- the credits cards are appended here, from CREDITS (producer's text, not the model's)."""
import json
import re

from . import config

VOICES = {
    "reader": {"label": "The reader", "accent": "secondary", "voice": "marin", "gemini_voice": "Laomedeia",
               "instructions": "Voice: the reader of a two-host podcast that compares films with the books they adapt. "
                               "She has read the novel closely. Affect: dry wit, precise, warm underneath, quick to "
                               "pounce on a detail. Pacing: brisk, conversational, real pauses before a reveal. Never "
                               "flat, never read aloud: she is talking to a friend across a table."},
    "viewer": {"label": "The viewer", "voice": "cedar", "pitch_semitones": -2, "gemini_voice": "Algenib",
               "instructions": "Voice: the viewer of a two-host podcast that compares films with the books they adapt. "
                               "He knows the film frame by frame. Affect: warm, amused, enjoys a punchline, concedes "
                               "gracefully. Pacing: lively, conversational. Never flat, never read aloud."},
}

COPY = "proxy"

# the voices credited must be the voices built: `episode --tts openai|gemini` (Gemini when its credit allows)
TTS = {"openai": dict(tts_spoken="OpenAI's", tts_line="gpt-4o-mini-tts (OpenAI): the two voices, marin and cedar (lowered two semitones)"),
       "gemini": dict(tts_spoken="Gemini's", tts_line="Gemini 3.8 Flash TTS (Google): the two voices, Laomedeia and Algenib; faster-whisper small for the line timing")}

CREDITS = [
    ("The works", "viewer",
     "The works: Red Alert, the novel by Peter George, 1958, and Dr. Strangelove, Stanley Kubrick's film of 1964.",
     ["Red Alert, novel by Peter George (as Peter Bryant), 1958; first published as Two Hours to Doom",
      "Dr. Strangelove or: How I Learned to Stop Worrying and Love the Bomb (1964), Columbia Pictures",
      "Directed and produced by Stanley Kubrick; screenplay by Stanley Kubrick, Terry Southern, Peter George",
      "With Peter Sellers, George C. Scott, Sterling Hayden, Keenan Wynn, Slim Pickens, Peter Bull, Tracy Reed, James Earl Jones",
      "Film stills are quoted for commentary and criticism; the novel is retold, not reproduced",
      "Also shown: posters of Fail Safe (1964, Sidney Lumet) and of Kubrick's other films"],
     "Rights remain with their holders."),
    ("Sources", "reader",
     "Our facts come from Philippe Vaugouin's movie database and its API, built on TMDb, Wikipedia and Wikidata, plus two critics' essays.",
     ["fastapi-text2sql API 1.1.19: film and source work sheets (TMDb, Wikipedia, Wikidata, IMDb rating)",
      "The Movie Database (TMDb): cast, crew, posters, portraits. This product uses the TMDb API but is not endorsed or certified by TMDb",
      "Wikipedia (CC BY-SA): Dr. Strangelove, Red Alert (novel), Fail Safe (1964 film)",
      "Turner Classic Movies, The Essentials: Dr. Strangelove (essay)",
      "F. Anthony Macklin, Sex and Dr. Strangelove, Film Comment, Summer 1965",
      "Art of the Title: the opening title sequence"],
     "Every fact line of the script cites one of these, a page of the novel or a subtitle of the film."),
    ("Models", "viewer",
     "The script was written by Claude, the voices are {tts_spoken}, and smaller open models aligned the book with the film.",
     ["Claude Opus 5.5 (Anthropic): comparison, outline, script and fact check, from the full novel, subtitles and database sheets",
      "{tts_line}",
      "BGE small en v1.5 (fastembed): alignment of novel passages with film dialogue",
      "CLIP ViT-B/32: which setting each shot of the film belongs to"],
     "The hosts are synthetic voices. They are not people, and they say so."),
    ("Software", "reader",
     "And the tools: source-to-screen, iconic-scenes and the voice-agent player, all open source, with ffmpeg underneath.",
     ["source-to-screen: the novel and the film aligned, the facts ledger, the Claude passes (github.com/vaugouin)",
      "iconic-scenes: film stills for a time span (github.com/vaugouin)",
      "voice-agent cinema player: audio build, stills, video (github.com/vaugouin)",
      "ffmpeg, Playwright and Chrome, Python and uv, RapidFuzz, fastembed"],
     None),
    ("Produced by Philippe Vaugouin", "viewer",
     "This episode was produced by Philippe Vaugouin. Thanks for listening.",
     ["Pilot episode of a series comparing films with the works they adapt (APP-IDEAS-010)",
      "Script checked against its sources by machine; produced and reviewed by Philippe Vaugouin"],
     "November 2026"),
]


def _ts(sec: float) -> str:
    h, m = int(sec // 3600), int(sec % 3600 // 60)
    return f"{h:02d}:{m:02d}:{sec - h * 3600 - m * 60:06.3f}"


def _time(s: str) -> float:
    parts = [float(x) for x in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def build(slug: str, tts: str = "openai") -> dict:
    p = config.pair(slug)
    sdir = config.work(slug, "script")
    script = config.load(sdir / "script.json")
    web = config.load(sdir / "web.json")
    cues = {c["id"]: c for c in config.load(config.work(slug, "subs") / "en-sdh.json")["cues"]}
    movie = config.load(config.work(slug, "facts") / "movie.json")
    work = config.load(config.work(slug, "facts") / "sourcework.json")
    offset = config.load(config.work(slug, "subs") / "offsets.json").get(COPY, {}).get("offset", 0.0)
    people = {}
    for c in (movie.get("cast") or []) + (movie.get("crew") or []):
        people.setdefault(c["PERSON_NAME"], dict(person_id=c["ID_PERSON"], name=c["PERSON_NAME"],
                                                 profile_path=c.get("PROFILE_PATH")))
    persons, related, problems = {}, {}, []
    # frames moved by hand after the eye check (beat id, or beat id + L/R for a split): exact frame
    ov_file = config.work(slug, "episode") / "frame-overrides.json"
    overrides = {k: v for k, v in (config.load(ov_file) if ov_file.exists() else {}).items() if not k.startswith("_")}

    def frame(spec: dict, key: str = "") -> dict:
        if key in overrides:
            return dict(movie_id=p["tmdb_movie_id"], copy=COPY, timecode=_ts(_time(overrides[key]) + offset), exact=True)
        if spec.get("cue"):
            c = cues[spec["cue"]]
            # inside the cue: the speaker of the line is on screen while saying it
            return dict(movie_id=p["tmdb_movie_id"], copy=COPY, timecode=_ts(c["start"] + offset),
                        window=[0.15, round(max(0.4, min(2.5, c["end"] - c["start"] - 0.1)), 2)])
        return dict(movie_id=p["tmdb_movie_id"], copy=COPY, timecode=_ts(_time(spec["time"]) + offset), window=[0.0, 1.5])

    def brick(v: dict, beat_id: str) -> dict:
        t = v.get("type", "hold")
        if t == "still":
            out = dict(type="quoted_frame" if v.get("quoted") else "frame", caption=v.get("caption", ""),
                       shows=v.get("shows", ""), **frame(v, beat_id))
            return out
        if t == "split":
            return dict(type="split_frames", caption=v.get("caption", ""),
                        left=dict(frame(v["left"], beat_id + "L"), shows=v["left"].get("shows", "")),
                        right=dict(frame(v["right"], beat_id + "R"), shows=v["right"].get("shows", "")))
        if t == "title_card":
            works = v.get("works", [])
            out = dict(type="title_card", caption=v.get("caption", ""))
            ids = [p["tmdb_movie_id"]] * ("film" in works) + [502] * ("failsafe" in works)
            if ids:
                out["movie_id"] = ids if len(ids) > 1 else ids[0]
            if "novel" in works:
                out["source_work_id"] = p["source_work_id"]
            return out
        if t == "portraits":
            ppl = []
            for x in v.get("people", []):
                person = people.get(x["name"])
                if not person:
                    problems.append(f"{beat_id}: no person '{x['name']}'")
                    continue
                persons[person["person_id"]] = person
                ppl.append(dict(person_id=person["person_id"], caption=x.get("caption", "")))
            return dict(type="portraits", people=ppl, caption=v.get("caption", "")) if ppl else dict(type="hold")
        if t == "posters":
            items = []
            for key in v.get("items", []):
                e = web["posters"].get(key)
                if not e:
                    problems.append(f"{beat_id}: no poster '{key}'")
                    continue
                related[e["id"]] = dict(kind="movie", id=e["id"], title=e["title"], year=e["year"], poster_path=e["poster_path"])
                items.append(dict(kind="movie", id=e["id"]))
            return dict(type="poster_wall", items=items, caption=v.get("caption", "")) if items else dict(type="hold")
        if t == "quote_card" and "paraphrase" in (v.get("attribution") or "").lower():
            return dict(v, type=t, paraphrase=True)
        if t in ("quote_card", "card", "hold"):
            return dict(v, type=t)
        problems.append(f"{beat_id}: unknown visual {t}")
        return dict(type="hold")

    beats = []
    for b in script["beats"]:
        src = [dict(type="ledger", id=r) for r in b.get("refs", [])] or [dict(type="none")]
        beat = dict(id=b["id"], voice=b["voice"], track=b["track"], text=b["text"], source=src,
                    brick=brick(b.get("visual") or {}, b["id"]), delivery=b.get("delivery", ""))
        if b.get("speech") and b["speech"] != b["text"]:
            beat["speech"] = b["speech"]
        if b.get("pause_after_ms"):
            beat["pause_after_ms"] = int(b["pause_after_ms"])
        beats.append(beat)
    if beats and beats[0]["brick"]["type"] == "hold":
        beats[0]["brick"] = dict(type="title_card", movie_id=p["tmdb_movie_id"], source_work_id=p["source_work_id"])
    for k, (title, voice, line, lines, source) in enumerate(CREDITS, 1):
        line, lines = line.format(**TTS[tts]), [x.format(**TTS[tts]) for x in lines]
        beats.append(dict(id=f"c{k:02d}", voice=voice, track="performance", text=line, source=[dict(type="none")],
                          brick=dict(type="card", variant="credits", title=title, lines=lines, source=source),
                          delivery="Plain, warm, unhurried: end credits.", pause_after_ms=2600 if k < len(CREDITS) else 4000))
    meta = dict(
        id=slug, title=script.get("title") or config.load(config.work(slug, "review") / "outline.json").get("title")
        or "Red Alert and Dr. Strangelove", language="en", version=3,
        angle="a novel and the film that turned it into a comedy, compared by a reader and a viewer",
        voices=VOICES,
        tts=dict(provider=tts, model="gemini-3.8-flash-tts" if tts == "gemini" else "gpt-4o-mini-tts",
                 fallback="openai"),
        register="reader / viewer (APP-IDEAS-010 §10.1): each host owns one work; script by Claude Opus 5.5 from "
                 "source-to-screen's corpus, checked for unknown ids and copied novel text.",
        works=[dict(movie_id=p["tmdb_movie_id"], title="Dr. Strangelove", year=1964, director="Stanley Kubrick",
                    runtime=movie.get("RUNTIME"), black_and_white=True, poster_path=movie.get("POSTER_PATH")),
               dict(movie_id=502, title="Fail Safe", year=1964, director="Sidney Lumet", runtime=112,
                    poster_path=web["posters"]["failsafe"]["poster_path"])],
        source_works=[dict(source_work_id=p["source_work_id"], name=work["SOURCE_WORK_NAME"], type="literary",
                           author="Peter George", year=work["SOURCE_WORK_YEAR"],
                           cover_url=work.get("WIKIPEDIA_MAIN_IMAGE_URL"))],
        copies={COPY: dict(movie_id=p["tmdb_movie_id"], file=p["copies"][COPY].replace("/", "\\"),
                           subtitle="source-to-screen work/strangelove/subs/en-sdh.json (master copy timeline)",
                           note=f"SDR 1080p copy on the master's timeline (offset {offset:+.3f} s, applied)")},
        persons=list(persons.values()), related=list(related.values()),
        chapters=script.get("chapters", []),
        fetched=dict(api="http://100.113.161.122:8187", endpoints=["/movies/935", "/sourceworks/10572", "/movies/502"],
                     date="2026-11-01"))
    scenario = dict(version=3, meta=meta, beats=beats)
    out = config.work(slug, "episode") / f"{slug}.json"
    config.save(out, scenario)
    return dict(path=str(out), beats=len(beats), persons=len(persons), posters=len(related), problems=problems)
