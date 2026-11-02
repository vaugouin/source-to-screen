# source-to-screen

## Canary

Start every reply with "Philippe,": no exceptions, including short replies and tool summaries.

## Purpose

Align a film or series with its source work (source text against subtitles and shots) to ground the APP-IDEAS-010 comparison podcast. Created 2026-11-01 by Nestor at Philippe's request; design and decisions in `~/Nestor/projets/t2s-backlog/app-ideas-010-podcast-generation-study.md` (§3.4 alignment, §6 evidence ledger, §8.1 pilot corpus, §10.1 decisions). What it does and commands: `README.md`; module roles: each module's docstring under `src/source_to_screen/`.

## Repository and versioning

- Public on GitHub: <https://github.com/vaugouin/source-to-screen>, code under MIT. `README.md` is the public description, in English, no em dashes.
- The version lives in `pyproject.toml` and `src/source_to_screen/__init__.py`: bump both (then `uv lock`) in every commit.
- **Never commit anything derived from the works**: epub text, subtitles, alignments, stills, all under `work/` (gitignored, with `*.epub`, `*.srt`, `.env`).
- To list in the ecosystem docs when it matures, as iconic-scenes is: profile README (`~/Code/vaugouin/README.md`), the About page (`~/Code/tmdb-front/lib/about.inc.php`), `tmdb-front/AGENTS.md`, `~/Nestor/projets/t2s-backlog/topics/related-repositories.txt`.

## Pairs and copies

- `data/pairs.json`: one entry per pair (slug, TMDb movie id, source work id, source text path, master copy, other copies, subtitle streams by copy, place aliases).
- **A timecode is valid for one file only.** Every output uses the master copy's timeline. Another copy's subtitles or shots may be used only after `offsets` shows `same_timeline: true` (constant offset, spread under 0.2 s, no drift); then add the measured offset.
- Strangelove: master is the UHD HDR10 copy (English and English SDH SRT); the MULTi copy carries the French tracks; the 1080p mp4 is 13 s longer (another timeline; iconic-scenes' War Room still came from it).

## Pitfalls (measured)

- **Epub spine order, not file names**: Calibre splits sort as split_1, split_10, split_2 (`text.spine`).
- **Munsey's-style epubs** put a whole chapter in one `<p>` and mark paragraphs with `<br/>`: `text._Blocks` splits on `<br>`.
- **Demuxing an embedded subtitle track reads the whole file** over the NAS: 11.7 MB/s on 2026-11-01, so about 8 minutes for a 5.7 GB copy. Do it once; `subs` skips tracks whose `.srt` exists.
- The embedding model is downloaded to `models/fastembed/` on first use (gitignored); a copy is kept in `C:\Users\vaugo\Data\soft\ai-models\bge-small-en-v1.5\` per the global rule; same for the CLIP pair (`clip-vit-b-32-vision`, `clip-vit-b-32-text`).
- **Settings come from the frames, not the dialogue** (`places.py`): talk of the bomb sounds alike in every set, so a dialogue-only guess put the last 40 minutes in the bomber. Method: one 320 px thumbnail per second, CLIP (fastembed `Qdrant/clip-ViT-B-32`) zero-shot on the prompts of `visual_places`; the surest seconds plus the seconds whose dialogue names exactly one setting (`dialogue_places`: "Mr. President", "Group Captain", "Kong") become image exemplars; k-NN vote; dialogue bonus; Viterbi smoothing; a shot takes the majority of its seconds. Prompts alone confused War Room close-ups with Ripper's office (19/24); the dialogue exemplars fixed it: 23/24 on the tuning sample, 24/24 on a fresh sample (2026-11-01). Image vectors are cached in `work/<pair>/places/images.npy` (computing them takes 10 min).
- **ffmpeg scdet** logs its cuts itself (`lavfi.scd.score: x, lavfi.scd.time: y` on one line): parse that, not `metadata=print`.
- **ASS tracks cannot be stream-copied to .srt**: `subs.extract` converts with `-c:s srt`.
- Strangelove offsets (2026-11-01): MULTi +0.078 s, 1080p FR EN x264 -0.020 s, both `same_timeline`.
- **The corpus must be byte-identical from run to run**, or the prompt cache is never read: `max(set(x), key=x.count)` breaks ties in set order, which changes between processes (string hash randomisation). Use `sorted(set(x))`. On 2026-11-01 this cost two full cache writes (about 1.6 $ each) before it was found; check with an md5 of `compare.corpus()` over two processes.
- **Save a paid answer before touching it**: `compare.ask` writes `work/last-answer.json` first. A crash on `msg._request_id` (absent on the streamed `ParsedMessage` of SDK 2.3) once lost a 2.85 $ answer.
- **Fuzzy anchors are candidates, not evidence**: partial-ratio 100 fires on short common phrases ("I think I do"). On the pilot, Claude marked 3 of the 6 as false and found the true sources; the `quotes` table of `compare.json` is the reference.
- **A still shows exactly what its line is about** (Philippe, 2026-11-02, for every podcast): the character who speaks a quoted line, on screen while saying it; the action a line describes, not the shot before or after. A cue's time is not enough: a line said over the loudspeaker or off screen falls on other shots (the base address of Strangelove is spoken by Ripper but plays over the gate and the computer room; Ripper is on screen only at 0:15:34-0:15:42; Kong's pep talk cuts to the crew at 0:10:42-0:11:05). Check every still by eye on a contact sheet before it ships, and move it inside the span where the subject is visible.
- Facts: the source work sheet carries the film's IMDb rating; `facts.py` drops IMDb fields from source works. The novel's Wikipedia plot in the API says the bomber is "shot down": wrong, the bomb falls and only the trigger fires (ch25.p012-p014).

## Claude passes (`compare.py`)

- **Prefer Claude on the plan over the API** (Philippe, 2026-11-02): from now on, a Claude pass (script, judge, revisions) is run by the Claude Code session itself or by a subagent, on the Max subscription, not through `ANTHROPIC_API_KEY`. The API passes below stay as a record and as a fallback.
- Strangelove script (2026-11-02): `script` in five parts (about 11,300 words, about 4 $ with the cache read), then `judge` (16 issues, all applied). A first single-part attempt at effort high spent its 64k output on thinking and wrote nothing (about 3.3 $ lost): keep the parts small and the effort at medium.

- Key: `ANTHROPIC_API_KEY` from `~/Code/fastapi-text2sql/.env` (Philippe's Individual Org, monthly Max plan credit), never printed. API facts: `TEXT2SQL_API_KEY` from `~/Code/text2sql-eval/.env`, green colour over Tailscale by default (`S2S_API_BASE` to change).
- Strangelove: corpus 205k tokens; compare 60k output tokens (2.85 $ with a cache write), outline 27k (2.30 $). With the cache read, a rerun of either pass costs about its output alone.
- Outputs under `work/<pair>/review/`: `corpus.txt`, `compare.json`, `outline.json`, their `.check.json` (usage, unknown ids, copied runs), `stop1.md`.

## Dependencies on other repos

- **iconic-scenes** (`~/Code/iconic-scenes`): stills for a time span of one file, `iconic-scenes still <file> <start> <end> --name <n> --out <dir>` (from 0.2.0).
- **fastapi-text2sql** API (`/movies/{id}`, `/sourceworks/{id}`) for facts, read by `facts.py`.
