# The paper

| Path | What it is |
|---|---|
| `journal/SentryGate-journal.pdf` | The paper. Built by `journal/build.py`. Never edit it by hand. |
| `journal/SentryGate-manuscript.docx` | The same paper as a Word manuscript. Built by `journal/build_docx_manuscript.py`. |
| `journal/paper.html`, `journal/parts/` | The source text of the paper. |
| `journal/manuscript/text.md` | The source text of the single-column manuscript. |
| `journal/figures/` | The data figures. Drawn by `journal/make_figures.py` from the result files. |
| `journal/diagrams/` | The architecture and harness diagrams. |
| `figures/` | Earlier charts, drawn by the scripts in `eval/`. |

## The rule

No number in the paper is typed by hand.
Every `{{token}}` in the source is filled in by `journal/build.py` from the committed result files in `data/`.
The build stops if a value is missing.

## Building it

```bash
make journal-figures   # draw the figures
make journal           # build the PDF (needs Google Chrome)
make journal-docx      # build the Word manuscript
```
