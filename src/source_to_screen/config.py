"""Paths and the pair registry (data/pairs.json). Everything derived from the works goes under work/<pair>/."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
WORK = Path(os.environ.get("S2S_WORK", ROOT / "work"))


def pairs() -> dict:
    return json.loads((DATA / "pairs.json").read_text(encoding="utf-8"))


def pair(slug: str) -> dict:
    p = pairs()[slug]
    p["slug"] = slug
    return p


def work(slug: str, *parts: str) -> Path:
    d = WORK / slug
    for part in parts:
        d = d / part
    d.mkdir(parents=True, exist_ok=True)
    return d


def video(p: dict, name: str) -> str:
    """'master' or a key of p['copies'] to a local path."""
    return p["master"] if name == "master" else p["copies"][name]


def save(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
