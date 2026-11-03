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
- actors shown as their characters, cut from the film (work/<pair>/portraits/char-*.jpg, copied to the assets);
- one still per shot (the same shot within 8 s becomes a hold); a frame checked by eye can be pinned in
  work/<pair>/episode/frame-overrides.json (beat id, or beat id + L/R);
- no evidence id on screen (card `source` dropped), chapter cards title only, posters panned on first sight;
- silent scrolling end credits from credits_roll() (the real sources; the producer for the production)."""
import json
import re

import shutil
import urllib.request

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

# Scrolling end credits, silent (Philippe, 2026-11-02): the real sources only; Philippe for the production.
def credits_roll(tts: str, writer: str = "claude") -> list[dict]:
    voices = ("Gemini 3.8 Flash TTS (Google), voices Laomedeia and Algenib" if tts == "gemini"
              else "gpt-4o-mini-tts (OpenAI), voices marin and cedar")
    return [
        dict(heading="Produced by", lines=["Philippe Vaugouin"]),
        dict(heading="Script", lines=["Claude Opus 5.5 (Anthropic), from the novel, the film and the sources below",
                                      "Every line checked against its source before recording"]) if writer == "claude" else
        dict(heading="Script", lines=["GPT-6.1 Sol (OpenAI, through Codex), from the novel, the film and the sources below",
                                      "Fact-checked line by line by Claude Opus 5.5 (Anthropic) before recording"]),
        dict(heading="Voices", lines=[voices, "The two hosts are synthetic voices"]),
        dict(heading="The novel", lines=["Red Alert, by Peter George (as Peter Bryant)",
                                         "First published in 1958 as Two Hours to Doom"]),
        dict(heading="The film", lines=["Dr. Strangelove or: How I Learned to Stop Worrying and Love the Bomb (1964)",
                                        "Directed and produced by Stanley Kubrick",
                                        "Screenplay by Stanley Kubrick, Terry Southern and Peter George",
                                        "Peter Sellers, George C. Scott, Sterling Hayden, Keenan Wynn, Slim Pickens",
                                        "Peter Bull, Tracy Reed, James Earl Jones",
                                        "A Columbia Pictures release"]),
        dict(heading="Also shown", lines=["Fail Safe (1964), directed by Sidney Lumet",
                                          "National Theatre Live: Dr. Strangelove (2025), with Steve Coogan"]),
        dict(heading="Sources", lines=["The Movie Database (TMDb): cast, crew, posters, portraits",
                                       "This product uses the TMDb API but is not endorsed or certified by TMDb",
                                       "Wikipedia (CC BY-SA): Dr. Strangelove, Red Alert (novel), Fail Safe (1964 film)",
                                       "Wikidata (CC0), IMDb ratings",
                                       "Turner Classic Movies, The Essentials: Dr. Strangelove",
                                       "F. Anthony Macklin, Sex and Dr. Strangelove, Film Comment, Summer 1965",
                                       "Art of the Title: Dr. Strangelove"]),
        dict(heading="Made with", lines=["source-to-screen, iconic-scenes, voice-agent (github.com/vaugouin)",
                                         "BGE small (fastembed), CLIP ViT-B/32, faster-whisper",
                                         "ffmpeg, Playwright, Chrome, Python, uv, RapidFuzz"]),
    ]


CREDITS_FOOTER = ("Film stills and posters are quoted for criticism and commentary. The novel is retold, not "
                  "reproduced. All rights remain with their holders.")

# Actors are shown as their characters, cut from the film (work/<pair>/portraits/char-<key>.jpg); a crew member
# or an actor without a crop keeps the TMDb portrait. Sellers without `as` gets his three parts.
CHARACTERS = {
    "Peter Sellers": {"mandrake": "mandrake", "muffley": "muffley", "president": "muffley", "strangelove": "strangelove"},
    "Sterling Hayden": {"": "ripper"}, "George C. Scott": {"": "turgidson"}, "Slim Pickens": {"": "kong"},
    "James Earl Jones": {"": "zogg"}, "Tracy Reed": {"": "missscott"}, "Peter Bull": {"": "desadesky"},
    "Keenan Wynn": {"": "guano"},
}
CHAR_LABEL = {"mandrake": "Group Captain Mandrake", "muffley": "President Muffley", "strangelove": "Dr. Strangelove",
              "ripper": "General Jack D. Ripper", "turgidson": "General Buck Turgidson", "kong": "Major T. J. Kong",
              "zogg": "Lt. Lothar Zogg", "missscott": "Miss Scott", "desadesky": "Ambassador de Sadesky",
              "guano": "Colonel Bat Guano"}
VOICE_AGENT_ASSETS = config.ROOT.parent / "voice-agent" / "cinema" / "assets"
TMDB_ORIGINAL = "https://image.tmdb.org/t/p/original"


def _ts(sec: float) -> str:
    h, m = int(sec // 3600), int(sec % 3600 // 60)
    return f"{h:02d}:{m:02d}:{sec - h * 3600 - m * 60:06.3f}"


def _time(s: str) -> float:
    parts = [float(x) for x in s.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _shot_of(shots: list, t: float) -> str | None:
    for sh in shots:
        if sh["start"] <= t < sh["end"]:
            return sh["id"]
    return None


def build(slug: str, tts: str = "gemini", variant: str = "") -> dict:
    """`variant` (e.g. "gpt"): another script of the same pair, read from work/<pair>/script-<variant>/, built as
    the episode <pair>-<variant> (its own scenario folder and voice-agent assets)."""
    p = config.pair(slug)
    sdir = config.work(slug, "script")
    script = config.load((config.work(slug, f"script-{variant}") if variant else sdir) / "script.json")
    web = config.load(sdir / "web.json")
    eid = f"{slug}-{variant}" if variant else slug
    edir = config.work(slug, f"episode-{variant}" if variant else "episode")
    cues = {c["id"]: c for c in config.load(config.work(slug, "subs") / "en-sdh.json")["cues"]}
    movie = config.load(config.work(slug, "facts") / "movie.json")
    work = config.load(config.work(slug, "facts") / "sourcework.json")
    offset = config.load(config.work(slug, "subs") / "offsets.json").get(COPY, {}).get("offset", 0.0)
    people = {}
    for c in (movie.get("cast") or []) + (movie.get("crew") or []):
        people.setdefault(c["PERSON_NAME"], dict(person_id=c["ID_PERSON"], name=c["PERSON_NAME"],
                                                 profile_path=c.get("PROFILE_PATH")))
    for name, x in web.get("extra_people", {}).items():
        people.setdefault(name, dict(person_id=x["person_id"], name=name, profile_path=x.get("profile_path")))
    persons, related, problems = {}, {}, []
    shots = config.load(config.work(slug, "shots") / "shots.json")["shots"]
    used_shots: set = set()   # one still per shot in the whole episode: a repeated shot becomes a hold
    shown_images: set = set()  # the first time a poster or cover appears, it pans
    assets = VOICE_AGENT_ASSETS / eid / "images"
    assets.mkdir(parents=True, exist_ok=True)
    for f in config.work(slug, "portraits").glob("char-*.jpg"):
        shutil.copyfile(f, assets / f.name)
    # frames moved by hand after the eye check (beat id, or beat id + L/R for a split): exact frame
    ov_file = edir / "frame-overrides.json"
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
            spec = frame(v, beat_id)
            at = _time(spec["timecode"]) + (spec.get("window") or [0, 0])[0]
            shot = _shot_of(shots, at)
            # the same shot within 8 s is the same picture (a long shot, the opening titles, may serve twice)
            if any(sh == shot and abs(t0 - at) < 8 for sh, t0 in used_shots):
                problems.append(f"{beat_id}: still in an already used shot ({shot}), held instead")
                return dict(type="hold")
            used_shots.add((shot, at))
            out = dict(type="quoted_frame" if v.get("quoted") else "frame", caption=v.get("caption", ""),
                       shows=v.get("shows", ""), **spec)
            if v.get("tag"):  # lower-third name tag, "Character · Actor", on a character's first still
                out["tag"] = v["tag"]
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
            key = json.dumps(works)
            if len(works) == 1 and works != ["novel"] and key not in shown_images:
                out["motion"] = "pan"  # first appearance of a poster or a cover: scrolled, then shown whole
            shown_images.add(key)
            return out
        if t == "portraits":
            ppl = []
            for x in v.get("people", []):
                person = people.get(x["name"])
                if not person:
                    problems.append(f"{beat_id}: no person '{x['name']}'")
                    continue
                persons[person["person_id"]] = person
                roles = CHARACTERS.get(x["name"])
                if roles:
                    as_ = (x.get("as") or "").lower()
                    keys = [k for w, k in roles.items() if w and w in as_] or (
                        [roles[""]] if "" in roles else ["mandrake", "muffley", "strangelove"])
                    for k in dict.fromkeys(keys):
                        ppl.append(dict(person_id=person["person_id"], image=f"images/char-{k}.jpg",
                                        name=CHAR_LABEL[k], caption=x["name"]))
                else:
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
            return dict(v, type=t, paraphrase=True, image="images/cover-10572.jpg")
        if t == "quote_card" and "kubrick" in (v.get("attribution") or "").lower():
            return dict(v, type=t, image="images/kubrick.jpg")
        if t == "card":
            out = {k: x for k, x in v.items() if k != "source"}  # no evidence ids on screen
            if out.get("variant") == "chapter":
                out.pop("lines", None)
            return dict(out, type=t)
        if t == "rename":  # the novel's name struck through, the film's typed in (2026-11-03)
            return dict(type=t, label=v.get("label", ""), novel=v["novel"], film=v["film"])
        if t == "teletype":  # a code or a message printed letter by letter on a teleprinter strip
            return dict(type=t, text=v["text"][:48], caption=v.get("caption", ""))
        if t in ("quote_card", "hold"):
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
    # chapter cards: "Chapter N" above the title
    starts = {c["beat"]: n for n, c in enumerate(script.get("chapters", []), 1)}
    for b in beats:
        if b["id"] in starts and b["brick"].get("type") == "card" and b["brick"].get("variant") == "chapter":
            b["brick"]["kicker"] = f"Chapter {starts[b['id']]}"
    if beats:
        beats[-1]["pause_after_ms"] = max(1500, beats[-1].get("pause_after_ms", 0))
    kubrick = assets / "kubrick.jpg"
    if not kubrick.exists() and people.get("Stanley Kubrick", {}).get("profile_path"):
        urllib.request.urlretrieve(TMDB_ORIGINAL + people["Stanley Kubrick"]["profile_path"], kubrick)
    meta = dict(
        id=eid, title=script.get("title") or config.load(config.work(slug, "review") / "outline.json").get("title")
        or "Red Alert and Dr. Strangelove", language="en", version=3,
        angle="a novel and the film that turned it into a comedy, compared by a reader and a viewer",
        voices=VOICES,
        tts=dict(provider=tts, model="gemini-3.8-flash-tts" if tts == "gemini" else "gpt-4o-mini-tts",
                 fallback="openai"),
        register="reader / viewer (APP-IDEAS-010 §10.1): each host owns one work; script by "
                 + ("GPT-6.1 Sol through Codex" if variant == "gpt" else "Claude Opus 5.5")
                 + " from source-to-screen's corpus, checked for unknown ids and copied novel text.",
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
        images=dict(tmdb_base=TMDB_ORIGINAL, tmdb_profile_size="original", tmdb_wall_size="original",
                    backdrop_url=TMDB_ORIGINAL + movie["BACKDROP_PATH"], backdrop_image="images/backdrop.jpg"),
        credits=credits_roll(tts, "gpt" if variant == "gpt" else "claude"), credits_footer=CREDITS_FOOTER,
        credits_subtitle="Red Alert, the novel, and Dr. Strangelove, the film",
        chapters=script.get("chapters", []),
        fetched=dict(api="http://100.113.161.122:8187", endpoints=["/movies/935", "/sourceworks/10572", "/movies/502"],
                     date="2026-11-01"))
    scenario = dict(version=3, meta=meta, beats=beats)
    out = edir / f"{eid}.json"
    config.save(out, scenario)
    return dict(path=str(out), beats=len(beats), persons=len(persons), posters=len(related), problems=problems)
