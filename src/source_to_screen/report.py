"""Review material from an alignment: the alignment curve (PNG), coverage by chapter, a Markdown summary.

Everything lands in work/<pair>/align/ and stays out of git: it quotes the works."""
import numpy as np

from . import config


def _place(b: dict) -> str:
    return b.get("place") or b["place_text"]


def _fmt(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


def curve(res: dict, dest) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    wins, blks = res["windows"], res["blocks"]
    colors = dict(zip(res["places"], ["#4e79a7", "#e15759", "#59a14f", "#f28e2b", "#b07aa1", "#76b7b2"]))
    fig, (ax, bar) = plt.subplots(2, 1, figsize=(12, 7.5), height_ratios=[5, 1], sharex=True)
    xs = [(b["start"] + b["end"]) / 120 for b in blks]
    ys = [wins[[w["id"] for w in wins].index(b["best"])]["i"] for b in blks]
    ax.scatter(xs, ys, s=[max(4, (b["best_sim"] - 0.5) * 120) for b in blks], c="#bbbbbb", label="best match (any order)")
    px = [(blks[p["block"]]["start"] + blks[p["block"]]["end"]) / 120 for p in res["path"]]
    py = [p["window"] for p in res["path"]]
    ax.plot(px, py, "-o", ms=3, lw=1, color="#222222", label="monotone path (kept, in order)")
    for a in res["anchors"]:
        j = next(w["i"] for w in wins if w["first"] <= a["source"] <= w["last"] and w["chapter"] == a["source"][:4])
        ax.scatter([a["start"] / 60], [j], marker="*", s=90, color="#d4a017", zorder=5)
    ticks = [w["i"] for k, w in enumerate(wins) if k == 0 or wins[k - 1]["chapter"] != w["chapter"]]
    ax.set_yticks(ticks, [wins[i]["chapter"] for i in ticks], fontsize=7)
    ax.set_ylabel("source text (chapter)")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(alpha=0.3)
    for b in blks:
        bar.axvspan(b["start"] / 60, b["end"] / 60, color=colors.get(_place(b), "#999999"))
    bar.set_yticks([])
    bar.set_xlabel("film time (minutes, master copy)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in colors.values()]
    bar.legend(handles, colors.keys(), loc="upper center", ncol=len(colors), fontsize=8, bbox_to_anchor=(0.5, -0.6))
    fig.suptitle(f"{res['pair']}: source text against film dialogue ({res['track']}, {res['model']})")
    fig.tight_layout()
    fig.savefig(dest, dpi=130)
    plt.close(fig)


def markdown(res: dict, text: dict) -> str:
    blks = res["blocks"]
    lines = [f"# {res['pair']}: alignment summary", "",
             f"Source: {text['words']} words, {len(text['chapters'])} chapters, {len(res['windows'])} windows. "
             f"Film: {len(blks)} dialogue blocks ({res['track']}). Match floor (cosine): {res['floor']}.", "",
             "## Coverage by chapter (share of source windows the film keeps: on the monotone path, or echoed in any order)", "",
             "| Chapter | Place | Words | Kept in order | Echoed anywhere | Windows |", "|---|---|---|---|---|---|"]
    for c in res["coverage"]:
        lines.append(f"| {c['chapter']} | {c['place']} | {c['words']} | {c['share']:.0%} | {c['echo_share']:.0%} | {c['windows']} |")
    lines += ["", "## Film dialogue time by place (from dialogue: draft until the frames decide)", "", "| Place | Minutes | Blocks |", "|---|---|---|"]
    for p in res["places"]:
        bs = [b for b in blks if _place(b) == p]
        lines.append(f"| {p} | {sum(b['end'] - b['start'] for b in bs) / 60:.1f} | {len(bs)} |")
    lines += ["", f"## Verbatim anchors ({len(res['anchors'])})", "", "| Film time | Source paragraph | Score | Film line |", "|---|---|---|---|"]
    for a in res["anchors"]:
        lines.append(f"| {_fmt(a['start'])} | {a['source']} | {a['score']} | {a['film'][:90]} |")
    lines += ["", "## Place sequence of the film", ""]
    run, start = None, 0.0
    for b in blks + [None]:
        pl = _place(b) if b else None
        if pl != run:
            if run:
                lines.append(f"- {_fmt(start)} to {_fmt(prev_end)}: {run}")
            run, start = pl, b["start"] if b else 0.0
        if b:
            prev_end = b["end"]
    return "\n".join(lines) + "\n"


def write(slug: str) -> list[str]:
    out = config.work(slug, "align")
    res = config.load(out / "alignment.json")
    text = config.load(config.work(slug, "text") / "source.json")
    curve(res, out / "alignment-curve.png")
    (out / "summary.md").write_text(markdown(res, text), encoding="utf-8")
    return [str(out / "alignment-curve.png"), str(out / "summary.md")]
