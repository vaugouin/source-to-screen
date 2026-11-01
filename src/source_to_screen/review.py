"""The document of review stop 1: work/<pair>/review/stop1.md, built from compare.json, outline.json
and the checker reports. Under work/ like everything derived from the works: never committed."""
from . import config


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        v = ", ".join(str(x) for x in v)
    return str(v).replace("|", "/").replace("\n", " ")


def table(rows: list[dict], cols: list[tuple[str, str]]) -> list[str]:
    out = ["| " + " | ".join(h for h, _ in cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(_cell(r.get(k)) for _, k in cols) + " |")
    return out


def write(slug: str) -> list[str]:
    d = config.work(slug, "review")
    c = config.load(d / "compare.json")
    cc = config.load(d / "compare.check.json")
    o = config.load(d / "outline.json") if (d / "outline.json").exists() else None
    oc = config.load(d / "outline.check.json") if (d / "outline.check.json").exists() else None
    L = [f"# {slug}: review stop 1 (comparison and outline)", ""]
    cost = cc["usage"]["cost_usd"] + (oc["usage"]["cost_usd"] if oc else 0)
    L += [f"Model: claude-opus-5-5. Cost of the two passes: {cost:.2f} $. Checker: {cc['cited']} ids cited in the "
          f"comparison, {len(cc['unknown'])} unknown, {len(cc['copies'])} runs of ten words copied from the novel"
          + (f"; outline {oc['cited']} ids, {len(oc['unknown'])} unknown, {len(oc['copies'])} copies." if oc else "."), ""]
    rel = c.get("relation", {})
    L += ["## Relation and thesis", "", f"- Label: {rel.get('label')}", f"- Mode: {rel.get('mode')}",
          f"- Thesis: {rel.get('thesis')}", ""]
    L += ["## Cardinal functions of the novel", ""]
    L += table(c.get("cardinal_functions", []), [("#", "n"), ("Novel", "novel"), ("Refs", "novel_refs"),
                                                 ("Film", "film"), ("Film note", "film_note"), ("Time", "film_time"),
                                                 ("Conf.", "confidence")])
    L += ["", "## Differences", ""]
    L += table(c.get("differences", []), [("Id", "id"), ("Lens", "lens"), ("Label", "label"), ("Novel", "novel"),
                                          ("Film", "film"), ("Time", "film_time"), ("Why", "explanation_kind"),
                                          ("Explanation", "explanation"), ("Effect", "effect"), ("Debate", "debate"),
                                          ("Novel refs", "novel_refs"), ("Evidence", "evidence"), ("Conf.", "confidence")])
    L += ["", "## Characters", ""]
    L += table(c.get("characters", []), [("Novel", "novel_name"), ("Film", "film_name"), ("Status", "status"),
                                         ("Actor", "actor"), ("Novel role", "novel_role"), ("Film role", "film_role"),
                                         ("Note", "note"), ("Refs", "novel_refs")])
    L += ["", "## Coverage, chapter by chapter", ""]
    L += table(c.get("coverage", []), [("Ch.", "chapter"), ("Setting", "setting"), ("Novel", "novel_summary"),
                                       ("On screen", "on_screen"), ("Film span", "film_span"), ("Note", "note")])
    L += ["", "## Inventions of the film", ""]
    L += table(c.get("inventions", []), [("What", "what"), ("Span", "film_span"), ("Why", "explanation_kind"),
                                         ("Explanation", "explanation")])
    L += ["", "## Lines kept from the novel", ""]
    L += table(c.get("quotes", []), [("Cue", "cue"), ("Time", "time"), ("Film line", "film_line"),
                                     ("Novel", "novel_ref"), ("Verdict", "verdict"), ("Note", "note")])
    L += ["", "## Settings", "", _cell(c.get("settings")), ""]
    for key, title in (("conflicts", "Conflicts between sources"), ("data_gaps", "Data gaps in the API")):
        L += [f"## {title}", ""]
        for x in c.get(key, []):
            L.append(f"- {_cell(x if isinstance(x, str) else '; '.join(f'{k}: {_cell(v)}' for k, v in x.items()))}")
        L.append("")
    if o:
        L += ["## Outline", "", f"**{o.get('title')}**, about {o.get('minutes_total')} minutes.", "",
              f"Thesis: {o.get('thesis')}", ""]
        for s in o.get("segments", []):
            L += [f"### {s.get('n')}. {s.get('title')} ({s.get('minutes')} min, lead: {s.get('lead')})", "",
                  f"Goal: {s.get('goal')}", ""]
            for b in s.get("beats", []):
                v = b.get("visual") or {}
                L.append(f"- **{b.get('who')}**: {b.get('beat')} *[{v.get('kind')}: {v.get('ref')}]* "
                         f"({_cell(b.get('evidence'))})")
            if s.get("debate"):
                L.append(f"- Debate: {s['debate']}")
            if s.get("rehook"):
                L.append(f"- Re-hook: {s['rehook']}")
            L.append("")
        L += ["### Stills to extract", ""]
        L += table(o.get("stills", []), [("Name", "name"), ("Start", "start"), ("End", "end"), ("Why", "why")])
        L += ["", "### Open points for the reviewer", ""]
        L += [f"- {_cell(x)}" for x in o.get("open_points", [])]
    if cc["unknown"] or cc["copies"] or (oc and (oc["unknown"] or oc["copies"])):
        L += ["", "## Checker findings", ""]
        for name, rep in (("comparison", cc), ("outline", oc)):
            if not rep:
                continue
            L += [f"- {name}, unknown id: `{t}` at {p}" for p, t in rep["unknown"]]
            L += [f"- {name}, copied run at {p}: \"{t}\"" for p, t in rep["copies"]]
    f = d / "stop1.md"
    f.write_text("\n".join(L) + "\n", encoding="utf-8")
    return [str(f)]
