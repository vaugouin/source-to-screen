"""Shot changes with ffmpeg's scdet filter, on a small decode of a light copy (no extra dependency).

The proxy must share the master's timeline (checked with subs.offset); its shot times then hold
for the master. Decoding at 320 px wide keeps a full film to a few minutes of CPU."""
import subprocess

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def detect(video: str, threshold: float = 10.0) -> list[dict]:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", video, "-an", "-sn", "-dn",
                           "-vf", f"scale=320:-2,scdet=threshold={threshold}:sc_pass=1,metadata=print", "-f", "null", "-"],
                          capture_output=True, text=True, errors="ignore", creationflags=NO_WINDOW, timeout=7200)
    times, scores = [], {}
    pending = None
    for line in proc.stderr.splitlines():
        if "lavfi.scd.score" in line:
            pending = float(line.rsplit("=", 1)[-1])
        elif "lavfi.scd.time" in line:
            t = float(line.rsplit("=", 1)[-1])
            times.append(t)
            scores[t] = pending
            pending = None
    return [dict(t=round(t, 3), score=scores.get(t)) for t in times]


def shots(cuts: list[dict], duration: float) -> list[dict]:
    edges = [0.0] + [c["t"] for c in cuts] + [duration]
    return [dict(id=f"shot.{i + 1:04d}", start=round(a, 3), end=round(b, 3)) for i, (a, b) in enumerate(zip(edges, edges[1:])) if b > a]


def duration(video: str) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                         capture_output=True, text=True, check=True, creationflags=NO_WINDOW, timeout=120)
    return float(out.stdout.strip())
