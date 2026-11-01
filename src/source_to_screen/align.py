"""Source text against the film's dialogue: windows, blocks, similarity, anchors, a monotone path, places.

Method (after Pial et al. 2023, simplified): the source is cut into windows of about 120 words
inside each chapter; the film's cues are grouped into dialogue blocks (a gap of more than 6 s or
60 s of length closes a block). Both are embedded locally (fastembed, bge-small-en-v1.5) and
compared by cosine. Three readings come out:

- anchors: a line of dialogue the film keeps almost word for word (RapidFuzz on quoted speech);
- best: for each film block, the source window it resembles most, in any order (shows reordering);
- path: one monotone alignment (dynamic programming with skips on both sides), the backbone of
  "what the film keeps, in the book's order".

Places: each film block gets the place whose source chapters it resembles most, smoothed so a
place holds for several blocks (Red Alert rotates between the bomber, the base and the Pentagon,
the film between the B-52, Burpelson and the War Room)."""
import re

import numpy as np
from rapidfuzz import fuzz

from . import config

MODEL = "BAAI/bge-small-en-v1.5"
WINDOW_WORDS = 120
BLOCK_GAP, BLOCK_MAX = 4.0, 30.0
SHARE_PENALTY = 0.6     # staying on one source window for one more film block costs this much (z units)
QUOTE = re.compile("[\"\u201c]([^\"\u201c\u201d]{12,}?)[\"\u201d]")


def windows(text: dict) -> list[dict]:
    out = []
    for ch in text["chapters"]:
        cur, words = [], 0
        for p in ch["paragraphs"]:
            cur.append(p)
            words += p["words"]
            if words >= WINDOW_WORDS:
                out.append(_window(ch, cur))
                cur, words = [], 0
        if cur:
            if words < WINDOW_WORDS / 3 and out and out[-1]["chapter"] == ch["id"]:
                last = out.pop()
                cur = last["_paras"] + cur
            out.append(_window(ch, cur))
    for i, w in enumerate(out):
        w["i"] = i
    return out


def _window(ch: dict, paras: list[dict]) -> dict:
    return dict(id=f"{paras[0]['id']}-{paras[-1]['id'].split('.')[-1]}", chapter=ch["id"], place=ch["place"],
                first=paras[0]["id"], last=paras[-1]["id"], words=sum(p["words"] for p in paras),
                text=" ".join(p["text"] for p in paras), _paras=paras)


def blocks(cues: list[dict]) -> list[dict]:
    out, cur = [], []
    for c in cues:
        if not c["text"]:
            continue
        if cur and (c["start"] - cur[-1]["end"] > BLOCK_GAP or c["end"] - cur[0]["start"] > BLOCK_MAX):
            out.append(cur)
            cur = []
        cur.append(c)
    if cur:
        out.append(cur)
    return [dict(id=f"blk.{i + 1:03d}", i=i, start=b[0]["start"], end=b[-1]["end"], cues=[c["id"] for c in b],
                 text=" ".join(c["text"] for c in b), speakers=sorted({s for c in b for s in c["speakers"]}))
            for i, b in enumerate(out)]


def embed(texts: list[str]) -> np.ndarray:
    from fastembed import TextEmbedding
    cache = config.ROOT / "models" / "fastembed"
    model = TextEmbedding(model_name=MODEL, cache_dir=str(cache))
    v = np.array(list(model.embed(texts)), dtype=np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def anchors(text: dict, cues: list[dict], min_score: int = 88, min_words: int = 6) -> list[dict]:
    """Lines of source dialogue the film keeps nearly verbatim."""
    quotes = [(p["id"], q.strip()) for ch in text["chapters"] for p in ch["paragraphs"] if p["dialogue"]
              for q in QUOTE.findall(p["text"]) if len(q.split()) >= 4]
    out = []
    for c in cues:
        t = c["text"]
        if len(t.split()) < min_words:
            continue
        best = max(((fuzz.token_set_ratio(t.lower(), q.lower()), pid, q) for pid, q in quotes), default=None)
        if best and best[0] >= min_score and fuzz.partial_ratio(t.lower(), best[2].lower()) >= min_score:
            out.append(dict(cue=c["id"], start=c["start"], film=t, source=best[1], source_text=best[2], score=round(best[0], 1)))
    return out


def path(sim: np.ndarray, skip: float = 0.0) -> list[tuple[int, int, float]]:
    """Monotone alignment of blocks (rows) to windows (columns) maximising the sum of (sim - mean) / std
    over matched pairs; skipping a block or a window costs `skip`. Several blocks may map to one window."""
    z = (sim - sim.mean()) / (sim.std() + 1e-9)
    n, m = z.shape
    score = np.full((n + 1, m + 1), -np.inf)
    back = np.zeros((n + 1, m + 1), dtype=np.int8)
    score[0, :] = 0.0
    score[:, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            opts = (score[i - 1, j - 1] + z[i - 1, j - 1],   # match, advance both
                    score[i - 1, j] + z[i - 1, j - 1] - SHARE_PENALTY,   # match, block shares the window
                    score[i - 1, j] - skip,                  # block unmatched (invented or changed)
                    score[i, j - 1] - skip)                  # window unmatched (cut)
            k = int(np.argmax(opts))
            score[i, j], back[i, j] = opts[k], k
    i, j = n, int(np.argmax(score[n]))
    out = []
    while i > 0 and j > 0:
        k = back[i, j]
        if k in (0, 1):
            out.append((i - 1, j - 1, float(sim[i - 1, j - 1])))
        if k == 0:
            i, j = i - 1, j - 1
        elif k in (1, 2):
            i -= 1
        else:
            j -= 1
    return out[::-1]


def places(sim: np.ndarray, wins: list[dict], stay: float = 0.6, k: int = 7) -> tuple[list[str], list[str]]:
    """Draft place of each film block from its dialogue: vote of the k most similar source windows,
    lightly smoothed (Viterbi). Dialogue about the bomb sounds alike in every setting, so this is a
    draft; the reliable place comes from the frames (shots)."""
    names = sorted({w["place"] for w in wins})
    top = np.argsort(-sim, axis=1)[:, :k]
    votes = np.array([[sum(wins[j]["place"] == p for j in row) for p in names] for row in top], dtype=float)
    logp = np.log((votes + 0.5) / (votes + 0.5).sum(axis=1, keepdims=True))
    k = len(names)
    trans = np.log(np.full((k, k), (1 - stay) / max(k - 1, 1)) + np.eye(k) * (stay - (1 - stay) / max(k - 1, 1)))
    v = logp[0].copy()
    back = []
    for t in range(1, len(logp)):
        cand = v[:, None] + trans
        back.append(cand.argmax(axis=0))
        v = cand.max(axis=0) + logp[t]
    seq = [int(v.argmax())]
    for b in reversed(back):
        seq.append(int(b[seq[-1]]))
    return [names[s] for s in seq[::-1]], names


def echoed(sim: np.ndarray, pct: float = 97) -> set[int]:
    """Windows that are some film block's best match, with a similarity in the top 3% of all pairs."""
    hi = float(np.percentile(sim, pct))
    best = sim.argmax(axis=1)
    return {int(best[i]) for i in range(len(best)) if sim[i, best[i]] >= hi}


def coverage(text: dict, wins: list[dict], matched: set[int], echoed: set[int]) -> list[dict]:
    """kept: windows on the monotone path (in order); echoed: windows some film block matches best, strongly (any order)."""
    out = []
    for ch in text["chapters"]:
        ws = [w for w in wins if w["chapter"] == ch["id"]]
        kept = [w for w in ws if w["i"] in matched]
        echo = [w for w in ws if w["i"] in echoed]
        out.append(dict(chapter=ch["id"], place=ch["place"], windows=len(ws), kept=len(kept), echoed=len(echo),
                        share=round(len(kept) / len(ws), 2) if ws else 0.0,
                        echo_share=round(len(echo) / len(ws), 2) if ws else 0.0, words=ch["words"]))
    return out


def run(slug: str, track: str = "en-sdh", match_floor: float | None = None) -> dict:
    text = config.load(config.work(slug, "text") / "source.json")
    cues = config.load(config.work(slug, "subs") / f"{track}.json")["cues"]
    wins, blks = windows(text), blocks(cues)
    vw, vb = embed([w["text"] for w in wins]), embed([b["text"] for b in blks])
    sim = vb @ vw.T
    floor = match_floor if match_floor is not None else float(np.percentile(sim, 90))
    p = path(sim)
    kept = [(i, j, s) for i, j, s in p if s >= floor]
    place_seq, place_names = places(sim, wins)
    best = sim.argmax(axis=1)
    for b, pl in zip(blks, place_seq):
        b["place_text"] = pl
        b["best"] = wins[int(best[b["i"]])]["id"]
        b["best_sim"] = round(float(sim[b["i"], best[b["i"]]]), 3)
    seen = config.work(slug, "places") / "places.json"
    if seen.exists():
        from .places import place_at
        vis = config.load(seen)
        for b in blks:
            b["place"] = place_at(vis, b["start"], b["end"])
        place_names = place_names + [p for p in vis["places"] if p not in place_names]
    on_path = {i: (j, s) for i, j, s in kept}
    for b in blks:
        if b["i"] in on_path:
            j, s = on_path[b["i"]]
            b["path"], b["path_sim"] = wins[j]["id"], round(s, 3)
    res = dict(pair=slug, track=track, model=MODEL, floor=round(floor, 3), places=place_names,
               windows=[{k: v for k, v in w.items() if k not in ("_paras", "text")} for w in wins],
               blocks=blks, anchors=anchors(text, cues), path=[dict(block=i, window=j, sim=round(s, 3)) for i, j, s in kept],
               coverage=coverage(text, wins, {j for _, j, _ in kept}, echoed(sim)))
    out = config.work(slug, "align")
    np.save(out / "sim.npy", sim)
    config.save(out / "alignment.json", res)
    return res
