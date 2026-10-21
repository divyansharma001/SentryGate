"""Build the Word version of the journal paper: paper/journal/SentryGate-journal.docx.

Reads the finished page that build.py writes (build/paper.html), so the Word
file says exactly what the PDF says: same text, same numbers, same tables.
It never adds words of its own.

Layout follows the PDF: title block and abstract across the page, body in two
Word columns, wide tables and figures across the page (Word continuous
section breaks), plain journal tables (top and bottom rules, a thin rule under
the header), running header and page numbers.

Figures: the charts come from make_figures.py as 300 dpi PNG; the two
diagrams are rendered to PNG with Chrome from the inline SVG in the page.

Run:  make journal-docx   (after make journal)
"""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt, RGBColor

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
PAGE = BUILD / "paper.html"
OUTPUT = HERE / "SentryGate-journal.docx"

FONT = "Times New Roman"
PAGE_W, PAGE_H = Cm(21.0), Cm(29.7)
MARGIN_LR, MARGIN_TB = Cm(1.55), Cm(1.7)
TEXT_W = PAGE_W - 2 * MARGIN_LR
GUTTER = Cm(0.7)
COL_W = (TEXT_W - GUTTER) // 2


# --- reading the built page into blocks ------------------------------------------------

class Node:
    def __init__(self, tag: str, attrs: dict, parent: "Node | None"):
        self.tag, self.attrs, self.parent, self.children = tag, attrs, parent, []

    def cls(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())

    def text(self) -> str:
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)


VOID = {"br", "img", "hr", "meta", "link", "path", "rect", "marker"}


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, dict(attrs), self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def find(node: Node, pred) -> list[Node]:
    out = []
    for c in node.children:
        if isinstance(c, Node):
            if pred(c):
                out.append(c)
            out += find(c, pred)
    return out


# --- low-level Word helpers ----------------------------------------------------------

def set_cols(section, n: int) -> None:
    cols = section._sectPr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        section._sectPr.append(cols)
    cols.set(qn("w:num"), str(n))
    cols.set(qn("w:space"), str(int(GUTTER.twips if hasattr(GUTTER, "twips") else GUTTER / 635)))


def new_section(doc, cols: int):
    sec = doc.add_section(WD_SECTION.CONTINUOUS)
    set_cols(sec, cols)
    return sec


def para_border(p, side: str, size_eighths: int) -> None:
    ppr = p._p.get_or_add_pPr()
    bdr = ppr.find(qn("w:pBdr"))
    if bdr is None:
        bdr = OxmlElement("w:pBdr")
        ppr.append(bdr)
    el = OxmlElement(f"w:{side}")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(size_eighths))
    el.set(qn("w:space"), "1")
    el.set(qn("w:color"), "000000")
    bdr.append(el)


def cell_borders(cell, **sides) -> None:
    tcpr = cell._tc.get_or_add_tcPr()
    bdr = tcpr.find(qn("w:tcBorders"))
    if bdr is None:
        bdr = OxmlElement("w:tcBorders")
        tcpr.append(bdr)
    for side, size in sides.items():
        el = OxmlElement(f"w:{side}")
        if size:
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), str(size))
            el.set(qn("w:color"), "000000")
        else:
            el.set(qn("w:val"), "nil")
        bdr.append(el)


def table_no_borders(table) -> None:
    tblpr = table._tbl.tblPr
    bdr = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "nil")
        bdr.append(el)
    tblpr.append(bdr)


def cell_margins(table, top=40, bottom=40, left=90, right=90) -> None:
    tblpr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for side, v in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(v))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tblpr.append(mar)


def keep_with_next(p) -> None:
    p.paragraph_format.keep_with_next = True


def fmt(p, size=10, align=WD_ALIGN_PARAGRAPH.JUSTIFY, indent=True, before=0, after=0, line=1.12):
    pf = p.paragraph_format
    pf.alignment = align
    pf.space_before, pf.space_after = Pt(before), Pt(after)
    pf.line_spacing = line
    pf.first_line_indent = Cm(0.5) if indent else None
    p._size = size
    return p


def add_runs(p, node, size: float, italic=False, bold=False, sup=False, sub=False, mono=False) -> None:
    """Write a node's inline content into paragraph p, keeping i, b, sup, sub."""
    for c in node.children if isinstance(node, Node) else [node]:
        if isinstance(c, str):
            text = re.sub(r"\s+", " ", c)
            if not text:
                continue
            r = p.add_run(text)
            r.font.name = "Courier New" if mono else FONT
            r.font.size = Pt(size - (1 if mono else 0))
            r.italic, r.bold = italic or None, bold or None
            if sup:
                r.font.superscript = True
            if sub:
                r.font.subscript = True
            continue
        if c.tag in ("style", "script"):
            continue
        if "nh" in c.cls():
            # Keep words like "Prompt-Injection" on one line (non-breaking hyphen).
            c.children = [x.replace("-", "\u2011") if isinstance(x, str) else x for x in c.children]
        add_runs(p, c, size,
                 italic=italic or c.tag in ("i", "em"),
                 bold=bold or c.tag in ("b", "strong"),
                 sup=sup or c.tag == "sup",
                 sub=sub or c.tag == "sub",
                 mono=mono or "mono" in c.cls())


def strip_edges(p) -> None:
    """Drop leading and trailing spaces, even when they sit in runs of their own."""
    for r in p.runs:
        r.text = r.text.lstrip()
        if r.text:
            break
    for r in reversed(p.runs):
        r.text = r.text.rstrip()
        if r.text:
            break



# Word checks the order of these children against its schema; python-docx and
# the helpers above append in whatever order they run, so sort before saving.
ORDER = {
    "pPr": "pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd "
           "tabs suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi "
           "adjustRightInd snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection "
           "textAlignment textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange",
    "tblPr": "tblStyle tblpPr tblOverlap bidiVisual tblStyleRowBandSize tblStyleColBandSize tblW jc tblCellSpacing "
             "tblInd tblBorders shd tblLayout tblCellMar tblLook tblCaption tblDescription",
    "tcPr": "cnfStyle tcW gridSpan hMerge vMerge tcBorders shd noWrap tcMar textDirection tcFitText vAlign hideMark",
    "tblBorders": "top left start bottom right end insideH insideV",
    "tcBorders": "top left start bottom right end insideH insideV tl2br tr2bl",
    "tblCellMar": "top left start bottom right end",
    "pBdr": "top left bottom right between bar",
}


def schema_order(root) -> None:
    for parent, names in ORDER.items():
        rank = {n: i for i, n in enumerate(names.split())}
        for el in root.iter(qn(f"w:{parent}")):
            kids = list(el)
            kids.sort(key=lambda k: rank.get(k.tag.split("}")[1], len(rank)))
            for k in kids:
                el.remove(k)
                el.append(k)


def fix_settings(doc) -> None:
    zoom = doc.settings.element.find(qn("w:zoom"))
    if zoom is not None and zoom.get(qn("w:percent")) is None:
        zoom.set(qn("w:percent"), "100")

# --- figures -----------------------------------------------------------------------

def chrome() -> str:
    for c in (os.environ.get("CHROME", ""), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome") or "", shutil.which("chromium") or ""):
        if c and Path(c).exists():
            return c
    raise SystemExit("Needs Google Chrome to render the diagrams.")


def render_svg(svg: str, name: str) -> Path:
    """Inline SVG from the page -> 3x PNG, via Chrome."""
    m = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    w, h = int(m.group(1)), int(m.group(2))
    page = BUILD / f"{name}.html"
    page.write_text(f'<!doctype html><html><body style="margin:0;background:#fff">'
                    f'<div style="width:{w}px;height:{h}px">{svg.replace("<svg ", f"<svg width={w} height={h} ", 1)}'
                    f"</div></body></html>")
    out = BUILD / f"{name}.png"
    subprocess.run([chrome(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=3",
                    f"--window-size={w},{h}", f"--screenshot={out}", page.as_uri()],
                   check=True, capture_output=True, timeout=60)
    return out


def svg_source(node: Node) -> str:
    """Rebuild the inline SVG markup of a figure from the raw page text."""
    return node.attrs["_raw"]


# --- the converter ----------------------------------------------------------------

class Converter:
    def __init__(self, raw_html: str):
        tree = Tree()
        tree.feed(raw_html)
        self.root = tree.root
        self.svgs = re.findall(r"<svg\b.*?</svg>", raw_html, re.S)
        self.svg_i = 0
        self.doc = Document()
        self.cols = 1

    def setup(self) -> None:
        doc = self.doc
        st = doc.styles["Normal"]
        st.font.name, st.font.size = FONT, Pt(10)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        sec = doc.sections[0]
        sec.page_width, sec.page_height = PAGE_W, PAGE_H
        sec.left_margin = sec.right_margin = MARGIN_LR
        sec.top_margin = sec.bottom_margin = MARGIN_TB
        sec.header_distance = sec.footer_distance = Cm(0.9)
        title = re.sub(r"\s+", " ", find(self.root, lambda n: n.tag == "title")[0].text()).strip()
        short = re.search(r'content: "([^"]+)"', open(PAGE).read())
        running = html.unescape(short.group(1)).replace("\\2013", "–").replace("  ", " ") if short else title
        hp = sec.header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = hp.add_run(running)
        r.italic, r.font.size, r.font.name = True, Pt(8.5), FONT
        fp = sec.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._page_field(fp)

    def _page_field(self, p) -> None:
        r = p.add_run()
        r.font.size, r.font.name = Pt(9), FONT
        for kind, text in (("begin", None), (None, " PAGE "), ("end", None)):
            if kind:
                el = OxmlElement("w:fldChar")
                el.set(qn("w:fldCharType"), kind)
            else:
                el = OxmlElement("w:instrText")
                el.set(qn("xml:space"), "preserve")
                el.text = text
            r._r.append(el)

    def ensure_cols(self, n: int) -> None:
        if self.cols != n:
            new_section(self.doc, n)
            self.cols = n

    # --- front matter ---
    def front(self) -> None:
        doc = self.doc
        h1 = find(self.root, lambda n: n.tag == "h1")[0]
        p = fmt(doc.add_paragraph(), align=WD_ALIGN_PARAGRAPH.LEFT, indent=False, after=8, line=1.05)
        add_runs(p, h1, 17, bold=True)
        strip_edges(p)
        for div in find(self.root, lambda n: n.tag == "div" and n.cls() & {"authors", "affil"}):
            size = 11 if "authors" in div.cls() else 9
            p = fmt(doc.add_paragraph(), align=WD_ALIGN_PARAGRAPH.LEFT, indent=False, after=2)
            add_runs(p, div, size, italic="affil" in div.cls())
            strip_edges(p)
        rule = fmt(doc.add_paragraph(), indent=False, before=6, after=8)
        para_border(rule, "bottom", 12)

        info = find(self.root, lambda n: "info" in n.cls())[0]
        abstract = find(self.root, lambda n: "abstract" in n.cls())[0]
        t = doc.add_table(rows=1, cols=2)
        table_no_borders(t)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        widths = (int(TEXT_W * 0.27), TEXT_W - int(TEXT_W * 0.27))
        for i, w in enumerate(widths):
            t.columns[i].width = w
            t.rows[0].cells[i].width = w
        left, right = t.rows[0].cells
        cell_borders(right, left=4)
        self._spaced_heading(left.paragraphs[0], "ARTICLE INFO")
        for pnode in find(info, lambda n: n.tag == "p"):
            text = pnode.text().strip()
            q = left.add_paragraph()
            fmt(q, size=8.6, align=WD_ALIGN_PARAGRAPH.LEFT, indent=False)
            if text:
                add_runs(q, pnode, 8.6)
                strip_edges(q)
        self._spaced_heading(right.paragraphs[0], "ABSTRACT", pad=True)
        q = right.add_paragraph()
        fmt(q, size=8.9, indent=False, line=1.1)
        q.paragraph_format.left_indent = Cm(0.35)
        body = Node("x", {}, None)
        body.children = [c for c in abstract.children if not (isinstance(c, Node) and c.tag == "h4")]
        add_runs(q, body, 8.9)
        strip_edges(q)
        rule = fmt(doc.add_paragraph(), indent=False, before=8, after=10)
        para_border(rule, "bottom", 6)

    def _spaced_heading(self, p, text: str, pad=False) -> None:
        fmt(p, align=WD_ALIGN_PARAGRAPH.LEFT, indent=False, after=5)
        if pad:
            p.paragraph_format.left_indent = Cm(0.35)
        r = p.add_run(" ".join(text))
        r.bold, r.font.size, r.font.name = True, Pt(8.6), FONT
        para_border(p, "bottom", 4)

    # --- body ---
    def body(self) -> None:
        cols = find(self.root, lambda n: n.tag == "div" and "cols" in n.cls())[0]
        self.ensure_cols(2)
        self.walk(cols)

    def walk(self, node: Node) -> None:
        for c in node.children:
            if isinstance(c, str):
                if c.strip():
                    p = fmt(self.doc.add_paragraph())
                    add_runs(p, c, 10)
                continue
            self.block(c)

    def block(self, n: Node) -> None:
        doc, cls = self.doc, n.cls()
        if n.tag == "h2":
            self.ensure_cols(2)
            p = fmt(doc.add_paragraph(), align=WD_ALIGN_PARAGRAPH.LEFT, indent=False, before=10, after=5)
            add_runs(p, n, 11, bold=True)
            strip_edges(p)
            for r in p.runs:
                r.text = r.text.upper()
            keep_with_next(p)
        elif n.tag == "h3":
            self.ensure_cols(2)
            p = fmt(doc.add_paragraph(), align=WD_ALIGN_PARAGRAPH.LEFT, indent=False, before=7, after=3)
            add_runs(p, n, 10, bold=True, italic=True)
            strip_edges(p)
            keep_with_next(p)
        elif n.tag == "p":
            self.ensure_cols(2)
            first = "nofirst" in cls or (n.attrs.get("style") or "").find("text-indent:0") >= 0
            p = fmt(doc.add_paragraph(), indent=not first)
            add_runs(p, n, 10)
            strip_edges(p)
        elif n.tag in ("ul", "ol"):
            self.ensure_cols(2)
            for li in find(n, lambda x: x.tag == "li"):
                p = fmt(doc.add_paragraph(style="List Bullet"), indent=False)
                p.paragraph_format.left_indent = Cm(0.55)
                p.paragraph_format.first_line_indent = Cm(-0.35)
                p.paragraph_format.space_after = Pt(1.5)
                add_runs(p, li, 10)
                strip_edges(p)
        elif n.tag == "div" and "eq" in cls:
            p = fmt(doc.add_paragraph(), align=WD_ALIGN_PARAGRAPH.LEFT, indent=False, before=4, after=4)
            ts = p.paragraph_format.tab_stops
            ts.add_tab_stop(COL_W // 2, WD_TAB_ALIGNMENT.CENTER)
            ts.add_tab_stop(COL_W, WD_TAB_ALIGNMENT.RIGHT)
            num = find(n, lambda x: "n" in x.cls())
            eq = Node("x", {}, None)
            eq.children = [c for c in n.children if not (isinstance(c, Node) and "n" in c.cls())]
            p.add_run("\t")
            add_runs(p, eq, 10, italic=True)
            p.add_run("\t" + (num[0].text() if num else ""))
        elif n.tag == "div" and "tbl" in cls:
            self.table(n, wide="span" in cls)
        elif n.tag == "figure":
            self.figure(n, wide="span" in cls)
        elif n.tag == "div" and "refs" in cls:
            self.ensure_cols(2)
            for pr in find(n, lambda x: x.tag == "p"):
                p = fmt(doc.add_paragraph(), size=8.6, align=WD_ALIGN_PARAGRAPH.LEFT, indent=False, after=3, line=1.05)
                p.paragraph_format.left_indent = Cm(0.55)
                p.paragraph_format.first_line_indent = Cm(-0.55)
                add_runs(p, pr, 8.6)
                strip_edges(p)
        elif n.tag in ("div", "span", "section"):
            self.walk(n)

    # --- tables ---
    def table(self, n: Node, wide: bool) -> None:
        doc = self.doc
        self.ensure_cols(1 if wide else 2)
        width = TEXT_W if wide else COL_W
        cap = find(n, lambda x: "cap" in x.cls())[0]
        p = fmt(doc.add_paragraph(), size=8.8, align=WD_ALIGN_PARAGRAPH.LEFT, indent=False, before=6, after=3)
        add_runs(p, cap, 8.8)
        strip_edges(p)
        keep_with_next(p)
        tnode = find(n, lambda x: x.tag == "table")[0]
        rows = find(tnode, lambda x: x.tag == "tr")
        cells = [[c for c in r.children if isinstance(c, Node) and c.tag in ("th", "td")] for r in rows]
        ncol = max(len(r) for r in cells)
        # Column widths from the longest text in each column, within limits.
        def natural(i: int) -> tuple[int, int]:
            """(full length, shortest it may get) of column i, in characters."""
            texts = [r[i].text().strip() for r in cells if i < len(r)]
            # A cell with no letters (a sum, a range) is one unbreakable piece.
            floor = max((len(t) if not any(ch.isalpha() for ch in t) else len(w)
                         for t in texts for w in (t.split() or [""])), default=1)
            return max(len(t) for t in texts) + 2, floor + 2

        sizes = [natural(i) for i in range(ncol)]
        weights = [full for full, _ in sizes]
        fits = int(width / 360000 * 7.2)   # characters that fit at 8.4 pt, roughly 7.2 per cm
        while sum(weights) > fits:
            # Shrink whichever column has the most room to give.
            slack = [w - low for w, (_, low) in zip(weights, sizes)]
            k = max(range(ncol), key=lambda j: slack[j])
            if slack[k] <= 0:
                break
            weights[k] -= 1
        total = sum(weights)
        widths = [int(width * w / total) for w in weights]
        widths[-1] = width - sum(widths[:-1])
        t = doc.add_table(rows=len(cells), cols=ncol)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        table_no_borders(t)
        cell_margins(t)
        for i, w in enumerate(widths):
            t.columns[i].width = w
        for ri, (row_node, row) in enumerate(zip(rows, cells)):
            row_cls = row_node.cls()
            for ci, cnode in enumerate(row):
                cell = t.rows[ri].cells[ci]
                cell.width = widths[ci]
                q = cell.paragraphs[0]
                left = "l" in cnode.cls()
                fmt(q, size=8.4, align=WD_ALIGN_PARAGRAPH.LEFT if left else WD_ALIGN_PARAGRAPH.CENTER,
                    indent=False, line=1.0)
                add_runs(q, cnode, 8.4, bold="best" in row_cls)
                strip_edges(q)
                sides = {}
                if ri == 0:
                    sides.update(top=10, bottom=5)
                if ri == len(cells) - 1:
                    sides["bottom"] = 10
                if "em" in row_cls:
                    sides["top"] = 5
                if sides:
                    cell_borders(cell, **sides)
            # Keep a row on one page.
            trpr = t.rows[ri]._tr.get_or_add_trPr()
            cant = OxmlElement("w:cantSplit")
            trpr.append(cant)
        sp = fmt(doc.add_paragraph(), indent=False, after=4)
        sp.paragraph_format.line_spacing = 0.6

    # --- figures ---
    def figure(self, n: Node, wide: bool) -> None:
        doc = self.doc
        self.ensure_cols(1 if wide else 2)
        width = TEXT_W if wide else COL_W
        style = n.attrs.get("style") or ""
        m = re.search(r"padding:\s*0\s+(\d+)%", style)
        if m:
            width = int(width * (1 - 2 * int(m.group(1)) / 100))
        img = find(n, lambda x: x.tag == "img")
        if img:
            src = img[0].attrs["src"].replace("../figures/", "").replace("figures/", "")
            path = HERE / "figures" / src.replace(".svg", ".png")
            im_style = img[0].attrs.get("style") or ""
            mw = re.search(r"width:\s*(\d+)%", im_style)
            if mw:
                width = int(width * int(mw.group(1)) / 100)
        else:
            svg = self.svgs[self.svg_i]
            self.svg_i += 1
            path = render_svg(svg, f"diagram-{self.svg_i}")
        p = fmt(doc.add_paragraph(), align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, before=6, after=2)
        p.add_run().add_picture(str(path), width=Emu(width))
        keep_with_next(p)
        cap = find(n, lambda x: x.tag == "figcaption")[0]
        q = fmt(doc.add_paragraph(), size=8.8, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, after=8)
        add_runs(q, cap, 8.8)
        strip_edges(q)

    def build(self) -> None:
        self.setup()
        self.front()
        self.body()
        self.doc.core_properties.title = re.sub(r"\s+", " ", find(self.root, lambda n: n.tag == "title")[0].text())
        self.doc.core_properties.author = "Divyansh Sharma, Sarvagya Dabas, Yashvit Gauri, Sandeep Singh"
        schema_order(self.doc.element.body)
        for sec in self.doc.sections:
            schema_order(sec.header._element)
            schema_order(sec.footer._element)
        fix_settings(self.doc)
        self.doc.save(OUTPUT)
        print(f"wrote {OUTPUT}")


def main() -> int:
    if not PAGE.exists():
        raise SystemExit("Build the paper first: python3 paper/journal/build.py")
    raw = PAGE.read_text()
    Converter(raw).build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
