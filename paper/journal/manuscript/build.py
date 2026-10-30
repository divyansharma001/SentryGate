"""Build the single-column, numbered-citation manuscript: paper/journal/manuscript/Manuscript.docx.

Sources:
    manuscript/text.md     the body text. {{token}} is a number filled from the
                           committed results by ../build.py; [@key,key] is a citation.
    manuscript/front.json  title block, abstract and keywords, as the authors edited them.
    ../build/paper.html    the tables, figures, equation and reference list of the paper.

Citations are numbered by first appearance, Table 1 included, and the reference
list follows that order. The build stops on an unknown key, an unused reference
or a missing number. Needs ../build.py --html to have run first.

Run:  make journal-manuscript
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
JOURNAL = HERE.parent
sys.path.insert(0, str(JOURNAL))

import build as paper  # noqa: E402
import build_docx_manuscript as M  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.shared import Cm, Pt  # noqa: E402

OUTPUT = HERE / "Manuscript.docx"

# Reference list order in the paper (alphabetical) -> citation key.
KEYS = ("bang2023 chen2023frugal chenS2025struq chenS2025secalign databricks2023 deepset2023 efron1993 field2007 "
        "gil2017 gill2025 greshake2023 gu2025 hackett2025 hanley1983 he2023 hines2024 inan2023 jain2023 "
        "jayavibhav2024 kettle2018 li2024 liang2026 liu2024 malkov2020 microsoft mirheidari2020 nguyen2019 ong2025 "
        "owasp2024 perez2022 protectai2024 qdrant rebedea2023 regmi2024 reimers2019 schroeder2026 song2025 "
        "vorobev2023 wang2020 wilson1927 wuG2026 wuG2025 wuX2026 yi2025 zhangZ2026a zhangZ2026b zheng2024").split()

# Table 1, first column -> (short name, key).
TABLE1 = {
    "Kettle (2018)": ("Kettle", "kettle2018"), "Nguyen et al. (2019)": ("Nguyen et al.", "nguyen2019"),
    "Mirheidari et al. (2020)": ("Mirheidari et al.", "mirheidari2020"),
    "Perez & Ribeiro (2022)": ("Perez and Ribeiro", "perez2022"), "Bang (2023)": ("Bang", "bang2023"),
    "Greshake et al. (2023)": ("Greshake et al.", "greshake2023"), "Liu et al. (2024)": ("Liu et al.", "liu2024"),
    "Gu et al. (2025)": ("Gu et al.", "gu2025"), "Song et al. (2025)": ("Song et al.", "song2025"),
    "Hackett et al. (2025)": ("Hackett et al.", "hackett2025"),
    "Schroeder et al. (2026)": ("Schroeder et al.", "schroeder2026"),
    "Wu, Wang, et al. (2026)": ("Wu, Wang et al.", "wuG2026"), "Wu, Ying, et al. (2026)": ("Wu, Ying et al.", "wuX2026"),
    "Zhang, Liu, et al. (2026)": ("Zhang, Liu et al.", "zhangZ2026a"),
    "Zhang, Yao, et al. (2026)": ("Zhang, Yao et al.", "zhangZ2026b"),
}

# Column widths in cm for each table, on the 16 cm text width.
WIDTHS = {"1": [3.3, 3.4, 5.5, 3.8], "2": [2.9, 7.3, 2.6, 3.2], "3": [1.0, 6.8, 4.8, 3.4], "4": [1.7, 4.5, 4.9, 4.9],
          "5": [4.6, 2.9, 2.9, 1.9, 1.9, 1.8], "6": [6.2, 1.8, 3.0, 5.0], "7": [4.6, 4.0, 4.0, 3.4]}

CITE = re.compile(r"\[@([A-Za-z0-9_,\s]+)\]")
TOKEN = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")
INLINE = re.compile(r"(\*[^*]+\*|`[^`]+`)")


class Numbers:
    def __init__(self):
        self.order: list[str] = []

    def num(self, key: str) -> int:
        if key not in KEYS:
            raise SystemExit(f"unknown citation key: {key}")
        if key not in self.order:
            self.order.append(key)
        return self.order.index(key) + 1

    def cite(self, keys: list[str]) -> str:
        """[3], [3, 7], or [3-5] for a run of three or more."""
        ns = sorted(self.num(k) for k in keys)
        groups, run = [], [ns[0]]
        for n in ns[1:]:
            if n == run[-1] + 1:
                run.append(n)
            else:
                groups.append(run)
                run = [n]
        groups.append(run)
        out = []
        for g in groups:
            out += [f"{g[0]}–{g[-1]}"] if len(g) > 2 else [str(x) for x in g]
        return "[" + ", ".join(out) + "]"


def fill(text: str, values: dict, nums: Numbers) -> str:
    def tok(m):
        if m.group(1) not in values:
            raise SystemExit(f"no value for {m.group(1)}")
        return html.unescape(values[m.group(1)])
    text = TOKEN.sub(tok, text)
    return CITE.sub(lambda m: nums.cite([k.strip() for k in m.group(1).split(",")]), text)


def write_inline(p, text: str, size: float) -> None:
    for chunk in INLINE.split(text):
        if not chunk:
            continue
        mono = chunk.startswith("`")
        ital = chunk.startswith("*")
        t = chunk[1:-1] if (mono or ital) else chunk
        r = p.add_run(t)
        r.font.name = "Courier New" if mono else M.FONT
        r.font.size = Pt(size - (1 if mono else 0))
        r.italic = True if ital else None


class Manuscript(M.Converter):
    def __init__(self, page_html: str, values: dict):
        super().__init__(page_html)
        self.values, self.nums = values, Numbers()
        self.tables = {}
        for n in M.find(self.root, lambda x: x.tag == "div" and "tbl" in x.cls()):
            self.tables[re.search(r"Table (\d+)", n.text()).group(1)] = n
        self.figures = {}
        for n in M.find(self.root, lambda x: x.tag == "figure"):
            cap = M.find(n, lambda x: x.tag == "figcaption")[0].text()
            self.figures[re.search(r"Fig\. (\d+)", cap).group(1)] = n

    def setup(self) -> None:
        super().setup()
        # A clean submission: no line numbers.
        sect = self.doc.sections[0]._sectPr
        ln = sect.find(M.qn("w:lnNumType"))
        if ln is not None:
            sect.remove(ln)

    def front(self) -> None:
        f = json.loads((HERE / "front.json").read_text())
        p = self.para("Title", WD_ALIGN_PARAGRAPH.CENTER, indent=False)
        r = p.add_run(f["title"])
        r.bold, r.font.size, r.font.name = True, Pt(16), M.FONT
        p = self.para(None, WD_ALIGN_PARAGRAPH.CENTER, indent=False)
        for i, (name, mark) in enumerate(f["authors"]):
            p.add_run(("" if i == 0 else ", ") + name)
            s = p.add_run(mark)
            s.font.superscript = True
        for mark, text in f["affiliations"]:
            p = self.para(None, WD_ALIGN_PARAGRAPH.CENTER, indent=False)
            p.paragraph_format.line_spacing = 1.15
            s = p.add_run(mark)
            s.font.superscript = True
            p.add_run(" " + text).italic = True
        p = self.para(None, WD_ALIGN_PARAGRAPH.CENTER, indent=False)
        p.paragraph_format.line_spacing = 1.15
        p.add_run("Email: " + f["emails"])
        p = self.para(None, WD_ALIGN_PARAGRAPH.CENTER, indent=False)
        p.paragraph_format.line_spacing = 1.15
        p.add_run("* Corresponding author: " + f["corresponding"])
        self.para("Heading 1", WD_ALIGN_PARAGRAPH.LEFT, indent=False).add_run("Abstract")
        self.para(indent=False).add_run(f["abstract"])
        p = self.para(None, WD_ALIGN_PARAGRAPH.LEFT, indent=False)
        p.add_run("Keywords: ").bold = True
        p.add_run("; ".join(f["keywords"]))

    def fixed_widths(self, n):
        cm = WIDTHS[re.search(r"Table (\d+)", n.text()).group(1)]
        return [int(Cm(x)) for x in cm]

    def table(self, n) -> None:
        if "Table 1" in n.text()[:12]:
            for row in M.find(n, lambda x: x.tag == "tr"):
                first = next(c for c in row.children if isinstance(c, M.Node))
                if first.tag == "td" and first.text().strip() in TABLE1:
                    name, key = TABLE1[first.text().strip()]
                    first.children = [f"{name} {self.nums.cite([key])}"]
        super().table(n)

    def text_block(self) -> None:
        lines = (HERE / "text.md").read_text().split("\n\n")
        after_heading = False
        for block in lines:
            b = block.strip()
            if not b:
                continue
            if b.startswith("# "):
                p = self.para("Heading 1", WD_ALIGN_PARAGRAPH.LEFT, indent=False)
                r = p.add_run(b[2:])
                r.bold = True
                after_heading = True
            elif b.startswith("## "):
                p = self.para("Heading 2", WD_ALIGN_PARAGRAPH.LEFT, indent=False)
                r = p.add_run(b[3:])
                r.bold, r.italic = True, True
                after_heading = True
            elif b.startswith("[[TABLE:"):
                self.table(self.tables[b[8:-2]])
            elif b.startswith("[[FIG:"):
                n = self.figures[b[6:-2]]
                self.figure(n, wide="span" in n.cls())
            elif b == "[[EQ]]":
                self.block(M.find(self.root, lambda x: x.tag == "div" and "eq" in x.cls())[0])
                after_heading = True
            elif b.startswith("- "):
                for item in b.split("\n"):
                    p = self.para("List Bullet", indent=False)
                    write_inline(p, fill(item[2:], self.values, self.nums), M.BODY_PT)
                after_heading = False
            else:
                p = self.para(indent=not after_heading)
                write_inline(p, fill(b, self.values, self.nums), M.BODY_PT)
                after_heading = False

    def references(self) -> None:
        refs = M.find(M.find(self.root, lambda x: x.tag == "div" and "refs" in x.cls())[0], lambda x: x.tag == "p")
        if len(refs) != len(KEYS):
            raise SystemExit(f"{len(refs)} references but {len(KEYS)} keys")
        unused = [k for k in KEYS if k not in self.nums.order]
        if unused:
            raise SystemExit(f"references never cited: {unused}")
        self.para("Heading 1", WD_ALIGN_PARAGRAPH.LEFT, indent=False).add_run("References").bold = True
        for i, key in enumerate(self.nums.order, 1):
            p = self.para(None, WD_ALIGN_PARAGRAPH.LEFT, indent=False)
            pf = p.paragraph_format
            pf.left_indent, pf.first_line_indent = Cm(0.9), Cm(-0.9)
            pf.space_after, pf.line_spacing = Pt(4), 1.15
            p.add_run(f"[{i}]\t").font.size = Pt(M.REF_PT)
            pf.tab_stops.add_tab_stop(Cm(0.9))
            M.add_runs(p, refs[KEYS.index(key)], M.REF_PT)
            for r in p.runs:
                r.text = r.text.replace("’", "'")

    def build(self) -> None:
        self.setup()
        self.front()
        self.text_block()
        self.references()
        self.doc.core_properties.title = json.loads((HERE / "front.json").read_text())["title"]
        self.doc.core_properties.author = "Divyansh Sharma, Yashvit Gauri, Sarvagya Dabas, Sandeep Singh"
        M.schema_order(self.doc.element.body)
        for sec in self.doc.sections:
            M.schema_order(sec.footer._element)
        M.fix_settings(self.doc)
        self.doc.save(OUTPUT)
        print(f"wrote {OUTPUT}  ({len(self.nums.order)} references)")


def main() -> int:
    if not M.PAGE.exists():
        raise SystemExit("Run: python3 paper/journal/build.py --html")
    Manuscript(M.PAGE.read_text(), paper.values()).build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
