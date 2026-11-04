"""Facts from the fastapi-text2sql API: the film sheet (/movies/{id}) and the source work sheet
(/sourceworks/{id}), stored raw, then flattened into ledger entries with stable ids.

Ledger ids: `api:m935.<field>` for a structured field, `api:m935.wiki.<section-slug>` for a
Wikipedia section, `api:sw10572.<...>` for the source work. The comparison pass may cite only
these ids, paragraph ids of the novel and cue ids of the subtitles; the checker refuses others.

Connection: TEXT2SQL_API_URL and TEXT2SQL_API_KEY from the environment or from the .env named by
S2S_API_ENV (default ~/Code/text2sql-eval/.env). The key is never printed."""
import json
import os
import re
import urllib.request
from datetime import date
from pathlib import Path

from . import config

ENV_FILE = Path(os.environ.get("S2S_API_ENV", Path.home() / "Code" / "text2sql-eval" / ".env"))


def _env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*([A-Za-z0-9_]+)\s*=\s*(.*)", line)
            if m:
                env[m[1]] = m[2].strip().strip('"')
    env.update({k: v for k, v in os.environ.items() if k.startswith("TEXT2SQL_")})
    return env


def get(path: str) -> dict:
    env = _env()
    base = env.get("TEXT2SQL_BASE_URL") or os.environ.get("S2S_API_BASE", "http://100.113.161.122:8186")
    req = urllib.request.Request(base.rstrip("/") + path, headers={"X-API-Key": env["TEXT2SQL_API_KEY"]})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


# Fields worth a ledger entry. IMDb fields are never taken from a source work sheet: they are the
# film's rating copied onto the work (a rating applies to films, series and episodes only).
FIELDS = {"MOVIE_TITLE", "ORIGINAL_TITLE", "DAT_RELEASE", "RUNTIME", "BUDGET", "REVENUE", "TAGLINE", "OVERVIEW",
          "IS_BLACK_AND_WHITE", "FILM_FORMAT", "ID_CRITERION_SPINE", "IMDB_RATING", "IMDB_VOTES", "ID_IMDB",
          "SOURCE_WORK_NAME", "SOURCE_WORK_TYPE", "SOURCE_WORK_YEAR", "ID_WIKIDATA"}
LISTS = {"genres", "companies", "production_countries", "based_on", "adapted_movies", "locations", "awards",
         "nominations", "mentions_movies", "mentioned_in_movies", "movies", "topics"}


def entries(prefix: str, sheet: dict, endpoint: str, version: str) -> list[dict]:
    """Scalars and short lists become one entry each; each Wikipedia section becomes one entry
    (its text kept whole for the comparison pass, which paraphrases and never quotes at length)."""
    today = date.today().isoformat()
    src = lambda p: dict(type="api", endpoint=endpoint, path=p, fetched=today, api_version=version)
    out = []
    for k, v in sheet.items():
        if v in (None, "", [], {}) or (prefix.startswith("sw") and k.startswith("IMDB")):
            continue
        if k in FIELDS and isinstance(v, (str, int, float, bool)):
            out.append(dict(id=f"api:{prefix}.{k.lower()}", claim=f"{k} = {v}", source=src(k)))
        elif k in LISTS and isinstance(v, list) and all(isinstance(x, dict) for x in v):
            for i, x in enumerate(v):
                short = {a: b for a, b in x.items() if isinstance(b, (str, int, float)) and b != ""
                         and not a.endswith(("_PATH", "_URL", "POPULARITY", "WEIGHTED"))}
                out.append(dict(id=f"api:{prefix}.{k.lower()}.{i}", claim=json.dumps(short, ensure_ascii=False)[:400],
                                source=src(f"{k}[{i}]")))
    for i, sec in enumerate(sheet.get("wikipedia_content") or []):
        title = sec.get("title") or sec.get("section") or f"s{i}"
        body = sec.get("content") or sec.get("text") or ""
        if body.strip():
            out.append(dict(id=f"api:{prefix}.wiki.{slug(title)}", claim=body.strip(), title=title,
                            source=src(f"wikipedia_content[{title}]")))
    for c in sheet.get("crew") or []:
        job = c.get("CREW_JOB") or c.get("job") or ""
        name = c.get("PERSON_NAME") or c.get("name")
        # jobs come comma-joined ("Director, Producer, Screenplay"): one entry per person
        out.append(dict(id=f"api:{prefix}.crew.{slug(name)}", claim=f"{name}: {job}", source=src("crew")))
    for c in (sheet.get("cast") or [])[:20]:
        name = c.get("PERSON_NAME") or c.get("name")
        role = c.get("CAST_CHARACTER") or c.get("character")
        out.append(dict(id=f"api:{prefix}.cast.{slug(name)}.{slug(role or '')}", claim=f"{name} as {role}", source=src("cast")))
    return out


def run(slug_: str) -> dict:
    p = config.pair(slug_)
    d = config.work(slug_, "facts")
    version = get("/").get("api_version", "?")
    film = get(f"/movies/{p['tmdb_movie_id']}")
    work = get(f"/sourceworks/{p['source_work_id']}")
    config.save(d / "movie.json", film)
    config.save(d / "sourcework.json", work)
    led = entries(f"m{p['tmdb_movie_id']}", film, f"/movies/{p['tmdb_movie_id']}", version) + \
        entries(f"sw{p['source_work_id']}", work, f"/sourceworks/{p['source_work_id']}", version)
    seen, uniq = set(), []
    for e in led:
        if e["id"] not in seen:
            seen.add(e["id"])
            uniq.append(e)
    config.save(d / "ledger-api.json", dict(api_version=version, entries=uniq))
    return dict(api_version=version, entries=len(uniq))
