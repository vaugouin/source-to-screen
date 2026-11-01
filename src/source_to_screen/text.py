"""Source text to chapters and paragraphs with stable ids (ch03.p012), from an epub.

The epub is read in its spine order (content.opf), not by file name: Calibre splits sort as
split_1, split_10, split_2. Chapter headings are kept as titles; a heading of the form
"Chapter 4. SONORA, TEXAS." also gives the chapter's place, which novels told in alternating
settings (Red Alert) use as scene headings."""
import html
import posixpath
import re
import zipfile
from html.parser import HTMLParser

BLOCKS = {"p", "div", "h1", "h2", "h3", "h4", "li", "blockquote"}
HEADINGS = {"h1", "h2", "h3"}
CHAPTER = re.compile(r"^\s*chapter\s+(\d+)\s*[.:]?\s*(.*?)\s*$", re.I)


class _Blocks(HTMLParser):
    """Collect (kind, text) for each block element; kind is 'h' for headings, 'p' otherwise."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.buf, self.kind, self.skip = [], [], "p", 0

    def flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if text:
            self.out.append((self.kind, text))
        self.buf, self.kind = [], "p"

    def handle_starttag(self, tag, attrs):
        if tag in ("head", "script", "style"):
            self.skip += 1
        elif tag in BLOCKS:
            self.flush()
            self.kind = "h" if tag in HEADINGS else "p"
        elif tag == "br":
            # Munsey's-style epubs put a whole chapter in one <p> and mark paragraphs with <br/>
            kind = self.kind
            self.flush()
            self.kind = kind

    def handle_endtag(self, tag):
        if tag in ("head", "script", "style"):
            self.skip -= 1
        elif tag in BLOCKS:
            self.flush()

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)


def spine(z: zipfile.ZipFile) -> list[str]:
    container = z.read("META-INF/container.xml").decode("utf-8", "ignore")
    opf = re.search(r'full-path="([^"]+)"', container).group(1)
    base = posixpath.dirname(opf)
    doc = z.read(opf).decode("utf-8", "ignore")
    items = {m.group(1): m.group(2) for m in re.finditer(r'<item\b[^>]*\bid="([^"]+)"[^>]*\bhref="([^"]+)"', doc)}
    items.update({m.group(2): m.group(1) for m in re.finditer(r'<item\b[^>]*\bhref="([^"]+)"[^>]*\bid="([^"]+)"', doc)})
    order = re.findall(r'<itemref\b[^>]*\bidref="([^"]+)"', doc)
    return [posixpath.normpath(posixpath.join(base, html.unescape(items[i]))) for i in order if i in items]


def clean(text: str) -> str:
    """Repair the usual mojibake of a Windows-1252 epub (curly quotes read as U+FFFD or C1 controls)."""
    text = text.replace("\u0091", "\u2018").replace("\u0092", "\u2019").replace("\u0093", "\u201c").replace("\u0094", "\u201d")
    text = text.replace("\u0096", "-").replace("\u0097", ", ").replace("\u2014", ", ").replace("\u2013", "-")
    return text.replace("�", "'")


def read_epub(path: str) -> dict:
    z = zipfile.ZipFile(path)
    chapters, front = [], []
    for name in spine(z):
        parser = _Blocks()
        parser.feed(z.read(name).decode("utf-8", "ignore"))
        parser.flush()
        for kind, text in parser.out:
            text = clean(text)
            m = CHAPTER.match(text) if kind == "h" else None
            if m:
                place = m.group(2).strip(" .'\"20182019201c201d")
                chapters.append(dict(n=int(m.group(1)), title=text, place=place, paragraphs=[]))
            elif kind == "h" and not chapters:
                front.append(dict(kind="heading", text=text))
            elif chapters:
                chapters[-1]["paragraphs"].append(text)
            else:
                front.append(dict(kind="text", text=text))
    out = []
    for ch in chapters:
        cid = f"ch{ch['n']:02d}"
        paras = [dict(id=f"{cid}.p{i:03d}", text=t, words=len(t.split()),
                      dialogue=bool(re.search(r"[\"201c201d]", t)))
                 for i, t in enumerate(ch["paragraphs"], 1)]
        out.append(dict(id=cid, n=ch["n"], title=ch["title"], place=ch["place"].title(),
                        words=sum(p["words"] for p in paras), paragraphs=paras))
    return dict(source=path, front=front, chapters=out, words=sum(c["words"] for c in out))
