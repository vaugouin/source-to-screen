"""Where each moment of the film takes place, from the frames: one thumbnail per second, CLIP zero-shot.

Dialogue alone cannot tell the settings apart (talk of the bomb sounds alike in the bomber, the
base and the War Room), but the pictures can: a cockpit, a round table under a ring of lights, an
office. Each place of the pair is described by a few prompts (data/pairs.json, `visual_places`);
the seconds the prompts are surest of become image exemplars, every second takes the vote of
its nearest exemplars, and a shot gets the majority of its seconds. Local model (fastembed, Qdrant/clip-ViT-B-32), no API call."""
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


def image_vectors(files: list[Path], cache_file: Path) -> np.ndarray:
    """CLIP image embeddings of the thumbnails, cached (about 10 min on the CPU for a 95 min film)."""
    if cache_file.exists():
        v = np.load(cache_file)
        if len(v) == len(files):
            return v
    from fastembed import ImageEmbedding
    cache = str(config.ROOT / "models" / "fastembed")
    v = np.array(list(ImageEmbedding(model_name=VISION, cache_dir=cache).embed([str(f) for f in files])), dtype=np.float32)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    np.save(cache_file, v)
    return v


def zero_shot(img: np.ndarray, prompts: dict[str, list[str]]) -> tuple[np.ndarray, list[str]]:
    from fastembed import TextEmbedding
    cache = str(config.ROOT / "models" / "fastembed")
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
    return per_place, places


def propagate(img: np.ndarray, scores: np.ndarray, seeds_per_place: int = 40, k: int = 15,
              extra: list[tuple[int, int]] | None = None) -> np.ndarray:
    """Self-training: the seconds the prompts are surest of (largest margin over the runner-up) become
    image exemplars of their place; every second then takes the vote of its k nearest exemplars.
    Image-to-image similarity recognises a set (the War Room, Ripper's office) far better than a prompt."""
    order = np.sort(scores, axis=1)
    margin = order[:, -1] - order[:, -2]
    best = scores.argmax(axis=1)
    seeds = []
    for c in range(scores.shape[1]):
        idx = np.where(best == c)[0]
        seeds += [(i, c) for i in idx[np.argsort(-margin[idx])][:seeds_per_place]]
    taken = {i for i, _ in seeds}
    seeds += [(i, c) for i, c in (extra or []) if i not in taken]
    si = np.array([i for i, _ in seeds])
    sc = np.array([c for _, c in seeds])
    sim = img @ img[si].T
    top = np.argsort(-sim, axis=1)[:, :k]
    votes = np.zeros_like(scores)
    for c in range(scores.shape[1]):
        votes[:, c] = ((sc[top] == c) * np.take_along_axis(sim, top, axis=1)).sum(axis=1)
    return votes


def dialogue_votes(p: dict, n: int, places: list[str], offset: float, weight: float = 0.6) -> np.ndarray:
    """Names and forms of address that belong to one setting ("Mr. President", "Group Captain", "Kong"),
    from data/pairs.json `dialogue_places`, add weight to that place for the seconds of the cue.
    Close-ups of men in suits look alike in two sets; who is addressed does not."""
    out = np.zeros((n, len(places)), dtype=np.float32)
    cues_file = config.work(p["slug"], "subs") / "en-sdh.json"
    if not cues_file.exists() or not p.get("dialogue_places"):
        return out
    for c in config.load(cues_file)["cues"]:
        text = c["text"].lower()
        for place, words in p["dialogue_places"].items():
            if place in places and any(w.lower() in text for w in words):
                a, b = int(max(0, c["start"] - offset)), int(min(n - 1, c["end"] - offset))
                out[a:b + 1, places.index(place)] += weight
    return out


def smooth(votes: np.ndarray, stay: float = 0.995, temp: float = 1) -> list[int]:
    """Viterbi over seconds: a setting holds for a while (a scene lasts minutes, a cut back is rare
    within seconds), so an isolated close-up that looks like another set keeps its scene's place."""
    v = votes / temp
    logp = v - np.log(np.exp(v - v.max(axis=1, keepdims=True)).sum(axis=1, keepdims=True)) - v.max(axis=1, keepdims=True)
    k = votes.shape[1]
    trans = np.log(np.where(np.eye(k, dtype=bool), stay, (1 - stay) / (k - 1)))
    score = logp[0].copy()
    back = np.zeros((len(v), k), dtype=np.int16)
    for t in range(1, len(v)):
        cand = score[:, None] + trans
        back[t] = cand.argmax(axis=0)
        score = cand.max(axis=0) + logp[t]
    seq = [int(score.argmax())]
    for t in range(len(v) - 1, 0, -1):
        seq.append(int(back[t][seq[-1]]))
    return seq[::-1]


def run(slug: str, copy: str = "proxy", offset: float = 0.0) -> dict:
    """Seconds are on `copy`'s timeline; `offset` (from subs.offset) moves them to the master's."""
    p = config.pair(slug)
    files = thumbnails(config.video(p, copy), config.work(slug, "thumbs"))
    img = image_vectors(files, config.work(slug, "places") / "images.npy")
    scores, places = zero_shot(img, p["visual_places"])
    talk = dialogue_votes(p, len(files), places, offset)
    # seconds whose dialogue names exactly one setting are exemplars too (precise, and they cover the
    # close-ups the prompts miss); every 3rd such second, at most 150 per place
    extra = []
    for c in range(len(places)):
        only = np.where((talk[:, c] > 0) & ((talk > 0).sum(axis=1) == 1))[0][::3][:150]
        extra += [(int(i), c) for i in only]
    votes = propagate(img, scores, extra=extra)
    votes = votes / (votes.sum(axis=1, keepdims=True) + 1e-9)
    votes += talk
    labels = [places[i] for i in smooth(votes)]
    seconds = [dict(t=round(i + 0.5 + offset, 2), place=lab) for i, lab in enumerate(labels)]
    shots_file = config.work(slug, "shots") / "shots.json"
    shots = config.load(shots_file)["shots"] if shots_file.exists() else []
    for s in shots:
        inside = [x["place"] for x in seconds if s["start"] + offset <= x["t"] < s["end"] + offset] or \
                 [min(seconds, key=lambda x: abs(x["t"] - (s["start"] + s["end"]) / 2 - offset))["place"]]
        s["place"] = max(sorted(set(inside)), key=inside.count)
    res = dict(copy=copy, offset=offset, places=places, seconds=seconds, shots=shots)
    np.save(config.work(slug, "places") / "votes.npy", votes)
    config.save(config.work(slug, "places") / "places.json", res)
    return res


def place_at(res: dict, start: float, end: float) -> str | None:
    """Majority place of the seconds within [start, end) on the master's timeline."""
    inside = [x["place"] for x in res["seconds"] if start <= x["t"] < end]
    # sorted, not set(): set order changes between processes, which made the corpus differ
    # from run to run and defeated the prompt cache
    return max(sorted(set(inside)), key=inside.count) if inside else None
