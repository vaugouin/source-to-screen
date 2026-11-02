# source-to-screen

Align a film or a series with the work it adapts (a novel, a play, a short story, an earlier film), so that a comparison of the two can be grounded in evidence rather than memory.

Give it a pair: the source text (an epub) and a copy of the film with subtitles. It cuts the source into chapters, paragraphs and windows of about 120 words, reads the film's subtitle tracks into timed cues, groups them into dialogue blocks, and compares the two with local sentence embeddings. Out come:

- **anchors**: lines of the source's dialogue that the film keeps almost word for word;
- **a best match** for every dialogue block of the film, in any order, which shows what was moved;
- **a monotone path**: what the film keeps of the source, in the source's order;
- **coverage by chapter**: how much of each chapter reaches the screen;
- **settings**: which setting each shot of the film belongs to, read from the frames (CLIP, with exemplars taken from the frames it is surest of and from lines that name a setting), set against the source's own place headings;
- **an alignment curve** (PNG) and a Markdown summary for review;
- **facts** from the fastapi-text2sql API (film sheet, source work sheet) as ledger entries with stable ids;
- **a script and a fact check**, then a **scenario** for voice-agent's cinema mode (two hosts, film stills, cards, credits);
- **a comparison and an outline** written by Claude from the whole source text, the whole subtitle track, the measures and the ledger: cardinal functions, differences with their explanation, characters, coverage chapter by chapter, inventions, the lines the film keeps, then a timed episode outline. A checker refuses any id that is not in the corpus and any run of ten words copied from the source.

It is the evidence layer of a generated two-host comparison podcast (APP-IDEAS-010 in the author's backlog): every claim of the script points to a paragraph id, a cue id or a timecode produced here. Stills for those timecodes come from [iconic-scenes](https://github.com/vaugouin/iconic-scenes) (`iconic-scenes still <file> <start> <end>`).

## Why local models, then Claude

The matching runs on the CPU with [fastembed](https://github.com/qdrant/fastembed) (`BAAI/bge-small-en-v1.5`, ONNX) and [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz): no API call, no token cost, the same result on every run. Claude comes after, in the comparison and outline passes (`claude-opus-5-5`, key `ANTHROPIC_API_KEY`), and reads this layer's output rather than its memory of the works: on the pilot it found that half of the fuzzy anchors were false and that the film keeps about thirty lines of the novel, most of them in the general's speech to his base.

## Method

After Pial et al. (2023), "Analyzing Film Adaptation through Narrative Alignment", simplified: cosine similarity between source windows and film dialogue blocks, then a dynamic-programming alignment that may skip on both sides (a skipped window is a cut, a skipped block is invented or changed material). Settings are read from one thumbnail per second: CLIP zero-shot on a few prompts per setting, then the surest seconds and the seconds whose dialogue names exactly one setting become image exemplars, a nearest-neighbour vote labels every second, and a Viterbi pass keeps a setting for the length of a scene.

## Usage

Requires Python 3.12 with [uv](https://docs.astral.sh/uv/), ffmpeg and ffprobe on the PATH.

```bash
uv run source-to-screen text strangelove      # epub to chapters and paragraphs
uv run source-to-screen subs strangelove      # demux and read the subtitle tracks named in data/pairs.json
uv run source-to-screen offsets strangelove   # do the other copies share the master's timeline?
uv run source-to-screen shots strangelove     # shot changes on a light copy (ffmpeg scdet)
uv run source-to-screen places strangelove    # setting of every second and shot, from the frames
uv run source-to-screen align strangelove     # embeddings, anchors, path, places, coverage
uv run source-to-screen report strangelove    # alignment curve and summary
uv run source-to-screen facts strangelove     # film and source work sheets from the API, as ledger entries
uv run source-to-screen compare strangelove   # Claude: comparison tables (about 205k input tokens, cached)
uv run source-to-screen outline strangelove   # Claude: timed outline, from the comparison
uv run source-to-screen review strangelove    # review document (work/<pair>/review/stop1.md)
uv run source-to-screen script strangelove    # Claude: the episode script in five parts, from the reviewed material
uv run source-to-screen judge strangelove     # Claude: every line checked against the ids it cites
uv run source-to-screen episode strangelove   # the script as a voice-agent cinema scenario (voices, stills, credits)
```

The scenario is then built and rendered by [voice-agent](https://github.com/vaugouin/voice-agent)'s cinema mode: `uv run tools/build-cinema-assets.py <scenario>` (frames, images, voices, timeline), then `uv run tools/render-cinema-stills.py <slug> --mp4` with the app running. Every film still is checked by eye on a contact sheet before the render: a still must show the speaker of its line, or the action it describes, and a still that does not is pinned to the right moment in `work/<pair>/episode/frame-overrides.json`.

Pairs are declared in `data/pairs.json`: the source text, the master copy (the one whose timecodes every output uses), the other copies and their subtitle streams.

## What is not in this repository

Everything derived from the works (text, subtitles, alignments, stills) is written under `work/`, which is never committed: the works are under copyright. Only code and the pair registry are public.

## Licence

MIT, see [LICENSE](LICENSE).
