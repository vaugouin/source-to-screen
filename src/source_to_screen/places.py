"""Where each moment of the film takes place, from the frames: one thumbnail per second, CLIP zero-shot.

Dialogue alone cannot tell the settings apart (talk of the bomb sounds alike in the bomber, the
base and the War Room), but the pictures can: a cockpit, a round table under a ring of lights, an
office. Each place of the pair is described by a few prompts (data/pairs.json, `visual_places`);
every second of the film gets the place whose prompts its thumbnail is closest to, and a shot
gets the majority of its seconds. Local model (fastembed, Qdrant/clip-ViT-B-32), no API call."""
import subprocess
from pathlib import Path

import numpy as np

from . import config

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
VISION, TEXT = "Qdrant/clip-ViT-B-32-vision", "Qdrant/clip-ViT-B-32-text"


def thumbnails(video: str, out: Path, fps: float = 1.0) -> list[Path]:
    """One 320 px frame per second, in one pass (reads the whole file)."""
    out.mkdir(parents=True, exist_ok=True)
    if not any(out.glob("t*.jpg")):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video, "-an", "-sn", "-dn",
                        "-vf", f"fps={fps},scale=320:-2", "-q:v", "4", "-y", str(out / "t%05d.jpg")],
                       check=True, creationflags=NO_WINDOW, timeout=7200)
    return sorted(out.glob("t*.jpg"))


def classify(files: list[Path], prompts: dict[str, list[str]]) -> tuple[list[str], np.ndarray, list[str]]:
    from fastembed import ImageEmbedding, TextEmbedding
    cache = str(config.ROOT / "models" / "fastembed")
    img = np.array(list(ImageEmbedding(model_name=VISION, cache_dir=cache).embed([str(f) for f in files])), dtype=np.float32)
    img /= np.linalg.norm(img, axis=1, keepdims=True)
    names, texts = [], []
    for place, ps in prompts.items():
        for p in ps:
            names.append(place)
            texts.append(p)
    txt = np.array(list(TextEmbedding(model_name=TEXT, cache_dir=cache).embed(texts)), dtype=np.float32)
    txt /= np.linalg.norm(txt, axis=1, keepdims=True)
    sim = img @ txt.T
    places = list(prompts)
    per_place = np.stack([sim[:, [i for i, n in enumerate(names) if n == p]].max(axis=1) for p in places], axis=1)
    return [places[i] for i in per_place.argmax(axis=1)], per_place, places


def run(slug: str, copy: str = "proxy", offset: float = 0.0) -> dict:
    """Seconds are on `copy`'s timeline; `offset` (from subs.offset) moves them to the master's."""
    p = config.pair(slug)
    files = thumbnails(config.video(p, copy), config.work(slug, "thumbs"))
    labels, scores, places = classify(files, p["visual_places"])
    seconds = [dict(t=round(i + 0.5 + offset, 2), place=lab) for i, lab in enumerate(labels)]
    shots_file = config.work(slug, "shots") / "shots.json"
    shots = config.load(shots_file)["shots"] if shots_file.exists() else []
    for s in shots:
        inside = [x["place"] for x in seconds if s["start"] + offset <= x["t"] < s["end"] + offset] or \
                 [min(seconds, key=lambda x: abs(x["t"] - (s["start"] + s["end"]) / 2 - offset))["place"]]
        s["place"] = max(set(inside), key=inside.count)
    res = dict(copy=copy, offset=offset, places=places, seconds=seconds, shots=shots)
    np.save(config.work(slug, "places") / "scores.npy", scores)
    config.save(config.work(slug, "places") / "places.json", res)
    return res


def place_at(res: dict, start: float, end: float) -> str | None:
    """Majority place of the seconds within [start, end) on the master's timeline."""
    inside = [x["place"] for x in res["seconds"] if start <= x["t"] < end]
    return max(set(inside), key=inside.count) if inside else None
