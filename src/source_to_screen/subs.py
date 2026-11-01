"""Subtitle tracks to cues with stable ids, SDH cleaning, and the offset between two tracks.

A timecode is valid for one file only: every cue file records the copy it came from. The SDH track
keeps what the plain track drops (speaker names, [sound cues], song titles): both are kept, the
SDH extras as separate fields, the spoken text cleaned for matching."""
import re
import statistics
import subprocess

import pysubs2
from rapidfuzz import fuzz

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SOUND = re.compile(r"[\[(]([^\])]+)[\])]")
SPEAKER = re.compile(r"^\s*-?\s*([A-Z][A-Z .'\-]{1,30}):\s*")
TAGS = re.compile(r"<[^>]+>|\{[^}]*\}")


def extract(video: str, stream: int, dest) -> None:
    """Demux one embedded text track as SRT (SubRip and ASS both convert; reads the whole file over the network: run once, keep the result)."""
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", video, "-map", f"0:{stream}",
                    "-c:s", "srt", "-y", str(dest)], check=True, creationflags=NO_WINDOW, timeout=3600)


def load(path, copy: str, track: str) -> dict:
    subs = pysubs2.load(str(path), encoding="utf-8")
    cues = []
    for ev in subs:
        if ev.is_comment:
            continue
        raw = TAGS.sub("", ev.text.replace("\\N", "\n")).strip()
        if not raw:
            continue
        sounds = [s.strip() for s in SOUND.findall(raw)]
        speakers, lines = [], []
        for line in SOUND.sub("", raw).split("\n"):
            m = SPEAKER.match(line)
            if m:
                speakers.append(m.group(1).strip().title())
                line = line[m.end():]
            line = line.strip(" -♪#")
            if line:
                lines.append(line)
        cues.append(dict(id=f"{track}.{len(cues) + 1:04d}", start=round(ev.start / 1000, 3), end=round(ev.end / 1000, 3),
                         text=" ".join(lines), raw=raw, speakers=speakers, sounds=sounds,
                         song="♪" in raw or "#" in raw))
    return dict(copy=copy, track=track, cues=cues)


def offset(a: list[dict], b: list[dict], min_len: int = 25, min_score: int = 92) -> dict:
    """Seconds to add to b's times to land on a's: median start delta over long cues whose text matches.
    Two rips of one cut give a constant delta (spread under 0.2 s); a drift or a large spread means
    another cut or another frame rate, and the timecodes must not be transferred."""
    longa = [c for c in a if len(c["text"]) >= min_len]
    deltas = []
    j0 = 0
    for c in b:
        if len(c["text"]) < min_len:
            continue
        best, best_s = None, 0
        for k in range(j0, len(longa)):
            if longa[k]["start"] - c["start"] > 120:
                break
            if c["start"] - longa[k]["start"] > 120:
                j0 = k
                continue
            s = fuzz.ratio(c["text"].lower(), longa[k]["text"].lower())
            if s > best_s:
                best, best_s = longa[k], s
        if best and best_s >= min_score:
            deltas.append((c["start"], best["start"] - c["start"]))
    if not deltas:
        return dict(matches=0)
    ds = [d for _, d in deltas]
    med = statistics.median(ds)
    half = len(deltas) // 2
    first, last = statistics.median(ds[:half] or ds), statistics.median(ds[half:] or ds)
    spread = statistics.median(abs(d - med) for d in ds)
    return dict(matches=len(deltas), offset=round(med, 3), spread=round(spread, 3),
                drift=round(last - first, 3), same_timeline=spread < 0.2 and abs(last - first) < 0.3)
