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

## Dependencies on other repos

- **iconic-scenes** (`~/Code/iconic-scenes`): stills for a time span of one file, `iconic-scenes still <file> <start> <end> --name <n> --out <dir>` (from 0.2.0).
- **fastapi-text2sql** API (`/movies/{id}`, `/sourceworks/{id}`) for facts; not called by this repo yet.
