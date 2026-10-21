"""Build the Word manuscript of the paper: paper/journal/SentryGate-journal.docx.

Reads the finished page that build.py writes (build/paper.html), so the Word
file says exactly what the PDF says: same text, same numbers, same tables.
It never adds words of its own.

The layout is the one journals ask for in a Word submission, not the
two-column look of the PDF (the publisher typesets that after acceptance):
single column, A4, 2.5 cm margins, Times New Roman 12 pt, 1.5 line spacing,
continuous line numbers for reviewers, Word's own Title, Heading, Caption and
List styles, editable tables with the caption above, figures inline with the
caption below, page numbers. No section breaks and no columns, so the layout
holds in Word, Pages, LibreOffice and Google Docs alike.

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
MARGIN_LR, MARGIN_TB = Cm(2.5), Cm(2.5)
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

BODY_PT, TABLE_PT, CAPTION_PT, REF_PT = 12, 10, 10, 11


def plain_style(style, size: float, bold=False, italic=False, before=0, after=0, line=1.5) -> None:
    """Times New Roman, black, no theme font or colour (the default template's headings are blue Calibri)."""
    style.font.name, style.font.size = FONT, Pt(size)
    style.font.bold, style.font.italic = bold, italic
    style.font.color.rgb = RGBColor(0, 0, 0)
    rpr = style.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if fonts.get(qn(attr)) is not None:
            del fonts.attrib[qn(attr)]
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attr), FONT)
    pf = style.paragraph_format
    pf.space_before, pf.space_after, pf.line_spacing = Pt(before), Pt(after), line


def line_numbers(section) -> None:
    """Continuous line numbers in the margin, for reviewers. Must sit after pgMar in sectPr."""
    ln = OxmlElement("w:lnNumType")
    ln.set(qn("w:countBy"), "1")
    ln.set(qn("w:restart"), "continuous")
    ln.set(qn("w:distance"), "283")
    sect = section._sectPr
    anchor = sect.find(qn("w:pgMar"))
    anchor.addnext(ln)


class Converter:
    def __init__(self, raw_html: str):
        tree = Tree()
        tree.feed(raw_html)
        self.root = tree.root
        self.svgs = re.findall(r"<svg\b.*?</svg>", raw_html, re.S)
        self.svg_i = 0
        self.doc = Document()

    # --- page and styles ---
    def setup(self) -> None:
        doc = self.doc
        st = doc.styles
        plain_style(st["Normal"], BODY_PT)
        plain_style(st["Title"], 16, bold=True, after=12, line=1.15)
        plain_style(st["Heading 1"], BODY_PT, bold=True, before=18, after=6)
        plain_style(st["Heading 2"], BODY_PT, bold=True, italic=True, before=12, after=4)
        plain_style(st["Caption"], CAPTION_PT, before=6, after=6, line=1.15)
        plain_style(st["List Bullet"], BODY_PT)
        for name in ("Title", "Heading 1", "Heading 2"):
            st[name].paragraph_format.keep_with_next = True
        # The Title style has a bottom border in the default template; journals do not.
        tp = st["Title"].element.find(qn("w:pPr"))
        if tp is not None and tp.find(qn("w:pBdr")) is not None:
            tp.remove(tp.find(qn("w:pBdr")))
        sec = doc.sections[0]
        sec.page_width, sec.page_height = PAGE_W, PAGE_H
        sec.left_margin = sec.right_margin = MARGIN_LR
        sec.top_margin = sec.bottom_margin = MARGIN_TB
        line_numbers(sec)
        fp = sec.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._page_field(fp)

    def _page_field(self, p) -> None:
        r = p.add_run()
        r.font.size, r.font.name = Pt(10), FONT
        for kind, text in (("begin", None), (None, " PAGE "), ("end", None)):
            if kind:
                el = OxmlElement("w:fldChar")
                el.set(qn("w:fldCharType"), kind)
            else:
                el = OxmlElement("w:instrText")
                el.set(qn("xml:space"), "preserve")
                el.text = text
            r._r.append(el)

    def para(self, style: str | None = None, align=WD_ALIGN_PARAGRAPH.JUSTIFY, indent=True):
        p = self.doc.add_paragraph(style=style) if style else self.doc.add_paragraph()
        p.paragraph_format.alignment = align
        p.paragraph_format.first_line_indent = Cm(0.75) if indent else None
        return p

    # --- title page ---
    def front(self) -> None:
        h1 = find(self.root, lambda n: n.tag == "h1")[0]
        p = self.para("Title", WD_ALIGN_PARAGRAPH.CENTER, indent=False)
        add_runs(p, h1, 16, bold=True)
        strip_edges(p)
        for div in find(self.root, lambda n: n.tag == "div" and n.cls() & {"authors", "affil"}):
            p = self.para(None, WD_ALIGN_PARAGRAPH.CENTER, indent=False)
            add_runs(p, div, BODY_PT, italic="affil" in div.cls())
            strip_edges(p)
        abstract = find(self.root, lambda n: "abstract" in n.cls())[0]
        h = self.para("Heading 1", WD_ALIGN_PARAGRAPH.LEFT, indent=False)
        h.add_run("Abstract")
        p = self.para(indent=False)
        body = Node("x", {}, None)
        body.children = [c for c in abstract.children if not (isinstance(c, Node) and c.tag == "h4")]
        add_runs(p, body, BODY_PT)
        strip_edges(p)
        info = find(self.root, lambda n: "info" in n.cls())[0]
        words = [pn.text().strip() for pn in find(info, lambda n: n.tag == "p")]
        words = [w for w in words if w and not w.lower().startswith("keywords")]
        p = self.para(None, WD_ALIGN_PARAGRAPH.LEFT, indent=False)
        p.paragraph_format.space_before = Pt(12)
        r = p.add_run("Keywords: ")
        r.bold = True
        p.add_run("; ".join(words))

    # --- body ---
    def body(self) -> None:
        cols = find(self.root, lambda n: n.tag == "div" and "cols" in n.cls())[0]
        self.walk(cols)

    def walk(self, node: Node) -> None:
        for c in node.children:
            if isinstance(c, Node):
                self.block(c)

    def block(self, n: Node) -> None:
        cls = n.cls()
        if n.tag == "h2":
            p = self.para("Heading 1", WD_ALIGN_PARAGRAPH.LEFT, indent=False)
            add_runs(p, n, BODY_PT, bold=True)
            strip_edges(p)
        elif n.tag == "h3":
            p = self.para("Heading 2", WD_ALIGN_PARAGRAPH.LEFT, indent=False)
            add_runs(p, n, BODY_PT, bold=True, italic=True)
            strip_edges(p)
        elif n.tag == "p":
            first = "nofirst" in cls or "text-indent:0" in (n.attrs.get("style") or "")
            prev = n.parent.children[:n.parent.children.index(n)]
            prev_tags = [x.tag for x in prev if isinstance(x, Node)]
            after_heading = bool(prev_tags) and prev_tags[-1] in ("h2", "h3")
            p = self.para(indent=not (first or after_heading))
            add_runs(p, n, BODY_PT)
            strip_edges(p)
        elif n.tag in ("ul", "ol"):
            for li in find(n, lambda x: x.tag == "li"):
                p = self.para("List Bullet", indent=False)
                add_runs(p, li, BODY_PT)
                strip_edges(p)
        elif n.tag == "div" and "eq" in cls:
            p = self.para(None, WD_ALIGN_PARAGRAPH.LEFT, indent=False)
            p.paragraph_format.space_before = p.paragraph_format.space_after = Pt(6)
            ts = p.paragraph_format.tab_stops
            ts.add_tab_stop(TEXT_W // 2, WD_TAB_ALIGNMENT.CENTER)
            ts.add_tab_stop(TEXT_W, WD_TAB_ALIGNMENT.RIGHT)
            num = find(n, lambda x: "n" in x.cls())
            eq = Node("x", {}, None)
            eq.children = [c for c in n.children if not (isinstance(c, Node) and "n" in c.cls())]
            p.add_run("\t")
            add_runs(p, eq, BODY_PT, italic=True)
            p.add_run("\t" + (num[0].text() if num else ""))
        elif n.tag == "div" and "tbl" in cls:
            self.table(n)
        elif n.tag == "figure":
            self.figure(n, wide="span" in cls)
        elif n.tag == "div" and "refs" in cls:
            for pr in find(n, lambda x: x.tag == "p"):
                p = self.para(None, WD_ALIGN_PARAGRAPH.LEFT, indent=False)
                pf = p.paragraph_format
                pf.left_indent, pf.first_line_indent = Cm(1.0), Cm(-1.0)
                pf.space_after, pf.line_spacing = Pt(6), 1.15
                add_runs(p, pr, REF_PT)
                strip_edges(p)
        elif n.tag in ("div", "span", "section"):
            self.walk(n)

    def caption(self, node: Node):
        """'Table 1.' or 'Fig. 1.' in bold, then the caption text in roman."""
        p = self.para("Caption", WD_ALIGN_PARAGRAPH.LEFT, indent=False)
        add_runs(p, node, CAPTION_PT)
        strip_edges(p)
        for r in p.runs:
            r.italic = None
        if p.runs and not p.runs[0].text.rstrip().endswith("."):
            p.runs[0].text = p.runs[0].text.rstrip() + "."
            if len(p.runs) > 1 and not p.runs[1].text.startswith(" "):
                p.runs[1].text = " " + p.runs[1].text
        return p

    # --- tables ---
    def table(self, n: Node) -> None:
        doc = self.doc
        width = TEXT_W
        cap = self.caption(find(n, lambda x: "cap" in x.cls())[0])
        cap.paragraph_format.keep_with_next = True
        tnode = find(n, lambda x: x.tag == "table")[0]
        rows = find(tnode, lambda x: x.tag == "tr")
        cells = [[c for c in r.children if isinstance(c, Node) and c.tag in ("th", "td")] for r in rows]
        ncol = max(len(r) for r in cells)

        def natural(i: int) -> tuple[int, int]:
            texts = [r[i].text().strip() for r in cells if i < len(r)]
            floor = max((len(t) if not any(ch.isalpha() for ch in t) else len(w)
                         for t in texts for w in (t.split() or [""])), default=1)
            return max(len(t) for t in texts) + 2, floor + 2

        sizes = [natural(i) for i in range(ncol)]
        weights = [full for full, _ in sizes]
        fits = int(width / 360000 * 6.2)   # characters per cm at 10 pt
        while sum(weights) > fits:
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
        cell_margins(t, top=30, bottom=30, left=80, right=80)
        for i, w in enumerate(widths):
            t.columns[i].width = w
        for ri, (row_node, row) in enumerate(zip(rows, cells)):
            row_cls = row_node.cls()
            for ci, cnode in enumerate(row):
                cell = t.rows[ri].cells[ci]
                cell.width = widths[ci]
                q = cell.paragraphs[0]
                q.paragraph_format.alignment = (WD_ALIGN_PARAGRAPH.LEFT if "l" in cnode.cls()
                                                else WD_ALIGN_PARAGRAPH.CENTER)
                q.paragraph_format.first_line_indent = None
                q.paragraph_format.line_spacing = 1.0
                add_runs(q, cnode, TABLE_PT, bold="best" in row_cls)
                strip_edges(q)
                # Word keeps a table on one page when every row but the last keeps with the next.
                q.paragraph_format.keep_with_next = ri < len(cells) - 1
                sides = {}
                if ri == 0:
                    sides.update(top=10, bottom=5)
                if ri == len(cells) - 1:
                    sides["bottom"] = 10
                if "em" in row_cls:
                    sides["top"] = 5
                if sides:
                    cell_borders(cell, **sides)
            trpr = t.rows[ri]._tr.get_or_add_trPr()
            trpr.append(OxmlElement("w:cantSplit"))
            if ri == 0:
                trpr.append(OxmlElement("w:tblHeader"))   # repeat the header on a new page
        spacer = self.para(indent=False)
        spacer.paragraph_format.space_after = Pt(6)

    # --- figures ---
    def figure(self, n: Node, wide: bool) -> None:
        width = TEXT_W if wide else int(TEXT_W * 0.62)
        img = find(n, lambda x: x.tag == "img")
        if img:
            src = img[0].attrs["src"].split("/")[-1]
            path = HERE / "figures" / src.replace(".svg", ".png")
        else:
            svg = self.svgs[self.svg_i]
            self.svg_i += 1
            path = render_svg(svg, f"diagram-{self.svg_i}")
        p = self.para(None, WD_ALIGN_PARAGRAPH.CENTER, indent=False)
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.keep_with_next = True
        p.add_run().add_picture(str(path), width=Emu(width))
        cap = self.caption(find(n, lambda x: x.tag == "figcaption")[0])
        cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.space_after = Pt(12)

    def build(self) -> None:
        self.setup()
        self.front()
        self.body()
        title = re.sub(r"\s+", " ", find(self.root, lambda n: n.tag == "title")[0].text()).strip()
        self.doc.core_properties.title = title
        self.doc.core_properties.author = "Divyansh Sharma, Sarvagya Dabas, Yashvit Gauri, Sandeep Singh"
        schema_order(self.doc.element.body)
        for sec in self.doc.sections:
            schema_order(sec.footer._element)
        fix_settings(self.doc)
        self.doc.save(OUTPUT)
        print(f"wrote {OUTPUT}")


def main() -> int:
    if not PAGE.exists():
        raise SystemExit("Build the paper first: python3 paper/journal/build.py")
    Converter(PAGE.read_text()).build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
