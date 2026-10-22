"""Small, safe rich text for letters: only bold, italic, underline, line breaks and paragraphs survive."""
from html import escape
from html.parser import HTMLParser

KEEP = {"b": "b", "strong": "b", "i": "i", "em": "i", "u": "u"}
BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "blockquote"}


class _Clean(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks, self.cur, self.open, self.skip = [], [], [], 0

    def _flush(self):
        for t in reversed(self.open):
            self.cur.append(f"</{t}>")
        html = "".join(self.cur).strip()
        self.blocks.append(html)
        self.cur = [f"<{t}>" for t in self.open]

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "template", "noscript"):
            self.skip += 1
        elif tag in KEEP:
            t = KEEP[tag]; self.open.append(t); self.cur.append(f"<{t}>")
        elif tag == "br":
            self.cur.append("<br>")
        elif tag in BLOCK and "".join(self.cur).strip():
            self._flush()

    def handle_endtag(self, tag):
        if tag in ("script", "style", "template", "noscript"):
            self.skip = max(0, self.skip - 1)
        elif tag in KEEP:
            t = KEEP[tag]
            if t in self.open:
                i = len(self.open) - 1 - self.open[::-1].index(t)
                for x in reversed(self.open[i:]):
                    self.cur.append(f"</{x}>")
                reopen = self.open[i + 1:]; self.open = self.open[:i] + reopen
                self.cur += [f"<{x}>" for x in reopen]
        elif tag in BLOCK:
            self._flush()

    def handle_data(self, data):
        if self.skip:
            return
        self.cur.append(escape(data.replace("\xa0", " ")))


def clean(html):
    """Editor HTML -> '<p>…</p>' blocks with only b/i/u/br inside. An empty line stays an empty paragraph."""
    p = _Clean(); p.feed(html or ""); p.close(); p._flush()
    blocks = p.blocks
    while blocks and blocks[-1] in ("", "<br>"):
        blocks.pop()
    while blocks and blocks[0] in ("", "<br>"):
        blocks.pop(0)
    return "".join(f"<p>{b if b and b != '<br>' else '<br>'}</p>" for b in blocks)


def from_plain(text):
    """Older letters were plain text: each line becomes a line, empty lines stay empty."""
    lines = (text or "").replace("\r\n", "\n").strip("\n").split("\n")
    return "".join(f"<p>{escape(l) if l.strip() else '<br>'}</p>" for l in lines)


# ------------------------------------------------------------------ documents (SOPs): headings and lists too
DOC_TAGS = {"b": "b", "strong": "b", "i": "i", "em": "i", "u": "u", "p": "p", "div": "p", "h1": "h3", "h2": "h3", "h3": "h3",
            "h4": "h3", "ul": "ul", "ol": "ol", "li": "li", "br": "br", "table": "table", "tr": "tr", "th": "th", "td": "td"}


class _Doc(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "template", "noscript"):
            self.skip += 1; return
        t = DOC_TAGS.get(tag)
        if t == "br":
            self.out.append("<br>")
        elif t:
            if t in ("p", "h3") and self.stack and self.stack[-1] in ("p", "h3"):
                self._close_to(len(self.stack) - 1)       # no paragraph inside a paragraph
            if t == "li" and "li" in self.stack:           # <li>One<li>Two – the first item ends where the next starts
                li = len(self.stack) - 1 - self.stack[::-1].index("li")
                lists = [i for i, x in enumerate(self.stack) if x in ("ul", "ol")]
                if not lists or li > lists[-1]:
                    self._close_to(li)
            self.stack.append(t); self.out.append(f"<{t}>")

    def _close_to(self, i):
        for t in reversed(self.stack[i:]):
            self.out.append(f"</{t}>")
        self.stack = self.stack[:i]

    def handle_endtag(self, tag):
        if tag in ("script", "style", "template", "noscript"):
            self.skip = max(0, self.skip - 1); return
        t = DOC_TAGS.get(tag)
        if t and t != "br" and t in self.stack:
            self._close_to(len(self.stack) - 1 - self.stack[::-1].index(t))

    def handle_data(self, data):
        if not self.skip:
            self.out.append(escape(data.replace("\xa0", " ")))


def clean_doc(html):
    """Editor HTML -> safe HTML with only headings (h3), paragraphs, bullet and numbered lists, bold/italic/underline."""
    import re
    p = _Doc(); p.feed(html or ""); p.close(); p._close_to(0)
    out = "".join(p.out)
    out = re.sub(r"<(p|h3|li|b|i|u)>\s*</\1>", "", out)        # empty bits left by the editor
    out = re.sub(r"<(ul|ol)>\s*</\1>", "", out)
    return out.strip()
