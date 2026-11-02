"""source-to-screen text|subs|offsets|shots|places|align|report|all|facts|compare|outline|review|script|episode <pair>"""
import argparse
import sys

from . import align, compare, config, episode, facts, places, report, review, script, shots, subs, text


def do_text(p: dict) -> None:
    res = text.read_epub(p["source_text"])
    aliases = p.get("places", {})
    for ch in res["chapters"]:
        ch["place_heading"] = ch["place"]
        ch["place"] = next((v for k, v in aliases.items() if ch["place"].lower().startswith(k.lower())), ch["place"])
    config.save(config.work(p["slug"], "text") / "source.json", res)
    print(f"text: {res['words']} words, {len(res['chapters'])} chapters")


def do_subs(p: dict) -> None:
    d = config.work(p["slug"], "subs")
    for track, spec in p["subtitles"].items():
        srt = d / f"{track}.srt"
        if not srt.exists():
            print(f"subs: demuxing {track} from {spec['file']} (reads the whole file)", flush=True)
            subs.extract(config.video(p, spec["file"]), spec["stream"], srt)
        res = subs.load(srt, spec["file"], track)
        config.save(d / f"{track}.json", res)
        print(f"subs: {track} {len(res['cues'])} cues from {spec['file']}")


def do_offsets(p: dict) -> None:
    """Does each other copy share the master's timeline? Measured on matching English cues."""
    d = config.work(p["slug"], "subs")
    master = config.load(d / "en.json")["cues"]
    out = {}
    others = {t: s for t, s in p["subtitles"].items() if s["file"] != "master" and t.startswith("en")}
    for track in others:
        out[p["subtitles"][track]["file"]] = subs.offset(master, config.load(d / f"{track}.json")["cues"])
    for name, extra in p.get("offset_tracks", {}).items():
        res = subs.load(extra, name, f"{name}-check")
        out[name] = subs.offset(master, res["cues"])
    config.save(d / "offsets.json", out)
    for k, v in out.items():
        print(f"offset: {k} {v}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="source-to-screen")
    ap.add_argument("step", choices=["text", "subs", "offsets", "shots", "places", "align", "report", "all",
                                     "facts", "compare", "outline", "review", "script", "judge", "episode"])
    ap.add_argument("--tts", default="openai", choices=["openai", "gemini"], help="voices credited and built (episode)")
    ap.add_argument("--parts", default="1,2,3,4,5", help="script parts to write, e.g. 2,3")
    ap.add_argument("pair", help="key of data/pairs.json, e.g. strangelove")
    ap.add_argument("--track", default="en-sdh", help="subtitle track for the alignment")
    ap.add_argument("--copy", default="proxy", help="copy used for shot detection (must share the master's timeline)")
    args = ap.parse_args()
    p = config.pair(args.pair)
    steps = ["text", "subs", "offsets", "shots", "places", "align", "report"] if args.step == "all" else [args.step]
    for step in steps:
        if step == "text":
            do_text(p)
        elif step == "subs":
            do_subs(p)
        elif step == "offsets":
            do_offsets(p)
        elif step == "shots":
            video = config.video(p, args.copy)
            cuts = shots.detect(video)
            dur = shots.duration(video)
            res = dict(copy=args.copy, duration=dur, cuts=cuts, shots=shots.shots(cuts, dur))
            config.save(config.work(p["slug"], "shots") / "shots.json", res)
            print(f"shots: {len(res['shots'])} shots on {args.copy}")
        elif step == "places":
            offs = config.work(p["slug"], "subs") / "offsets.json"
            off = config.load(offs).get(args.copy, {}) if offs.exists() else {}
            if args.copy != "master" and not off.get("same_timeline"):
                print(f"places: {args.copy} is not proven to share the master's timeline, run offsets first")
                return
            res = places.run(p["slug"], args.copy, off.get("offset", 0.0))
            counts = {pl: sum(x["place"] == pl for x in res["seconds"]) for pl in res["places"]}
            print(f"places: {len(res['seconds'])} seconds, {len(res['shots'])} shots, {counts}")
        elif step == "align":
            res = align.run(p["slug"], args.track)
            print(f"align: {len(res['blocks'])} blocks, {len(res['windows'])} windows, {len(res['path'])} kept, "
                  f"{len(res['anchors'])} anchors")
        elif step == "report":
            for f in report.write(p["slug"]):
                print(f"report: {f}")
        elif step == "facts":
            print(f"facts: {facts.run(p['slug'])}")
        elif step in ("compare", "outline"):
            print(f"{step}: {compare.run(p['slug'], step)}")
        elif step == "review":
            for f in review.write(p["slug"]):
                print(f"review: {f}")
        elif step == "script":
            print(f"script: {script.run(p['slug'], [int(x) for x in args.parts.split(',')])}")
        elif step == "judge":
            print(f"judge: {script.judge(p['slug'])}")
        elif step == "episode":
            print(f"episode: {episode.build(p['slug'], args.tts)}")


if __name__ == "__main__":
    sys.exit(main())
