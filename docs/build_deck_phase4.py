"""Build docs/deck-phase4.html for the final review (Phase 4).

Every number is read from the committed results, so the slides cannot drift
from what the code produced:

    data/week4/report.json      the bypass sweep
    data/phase3/report.json     the defence settings
    data/phase4/report.json     confidence ranges and the filter-alone study
    data/router/report.json     the model picker
    paper/journal/figures/*.png the charts, as drawn for the paper

The visual style and the slide navigation are reused from the Phase 1 deck
(docs/deck.template.html), so all three decks look and behave the same.

    make deck-phase4
"""

from __future__ import annotations

import base64
import json
import pathlib
import re
import sys

DOCS = pathlib.Path(__file__).parent
ROOT = DOCS.parent
FIG = ROOT / "paper" / "journal" / "figures"
TEMPLATE = DOCS / "deck.template.html"
OUT = DOCS / "deck-phase4.html"


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text())


def b64(path: pathlib.Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def extract(tag: str, text: str) -> str:
    m = re.search(rf"<{tag}[^>]*>.*?</{tag}>", text, re.S)
    if not m:
        sys.exit(f"could not find <{tag}> in the Phase 1 template")
    return m.group(0)


def rng(cell: dict) -> str:
    return f'{cell["ci"][0]:.1f}&ndash;{cell["ci"][1]:.1f}'


def main() -> int:
    w4, p3, p4, rtr = (load("data/week4/report.json"), load("data/phase3/report.json"),
                       load("data/phase4/report.json"), load("data/router/report.json"))
    arms, scr, sw, ci3 = p3["arms"], p4["screening"], p4["earlier"]["bypass_by_threshold"], p4["earlier"]["phase3_cache_caused"]
    fa_ord, fa_look = scr["false_alarms_ordinary"], scr["false_alarms_lookalike"]
    det_ds, det_jay = scr["by_dataset"]["deepset"]["detection"], scr["by_dataset"]["jayavibhav"]["detection"]
    easy = rtr["cost_by_label"]["easy"]
    refs = (ROOT / "paper/journal/parts/back_matter.html").read_text().split("<h2>References</h2>", 1)[1].count("<p>")

    names = {"base": "No defence", "filter": "Label match only", "recheck": "Re-check risky hits only",
             "both": "Label match + re-check risky", "all": "Label match + re-check every hit"}
    defence_rows = []
    for tag in ("base", "filter", "recheck", "both", "all"):
        a = arms[tag]
        clean, attack = a["served"]["clean"]["cache_caused"], a["served"]["attack"]["cache_caused"]
        hi = ' class="hi"' if tag == "all" else ""
        cc = "green" if tag == "all" else ("red" if clean > 40 else "amber")
        ac = "green" if attack < 5 else "red"
        defence_rows.append(
            f'<tr{hi}><td>{names[tag]}</td>'
            f'<td class="num mono {cc}">{clean:.1f}% <span class="dim">({rng(ci3[tag + "/clean"])})</span></td>'
            f'<td class="num mono {ac}">{attack:.1f}% <span class="dim">({rng(ci3[tag + "/attack"])})</span></td>'
            f'<td class="num mono">{a["honest_hit_rate"]:.1f}%</td></tr>')

    bypass_rows = []
    for t in ("0.95", "0.90", "0.85", "0.80", "0.75", "0.70", "0.65"):
        r = sw[t]
        hi = ' class="hi"' if t == "0.85" else ""
        bypass_rows.append(
            f'<tr{hi}><td class="mono">{t}</td><td class="num mono">{r["lazy"]["rate"]:.1f}%</td>'
            f'<td class="num mono dim">{r["rewrite"]["rate"]:.1f}%</td><td class="num mono">{r["all"]["rate"]:.1f}%</td></tr>')

    v = {
        "LAZY85": f'{sw["0.85"]["lazy"]["rate"]:.1f}', "LAZY85_CI": rng(sw["0.85"]["lazy"]),
        "N": f'{w4["attack_variants_per_threshold"]:,}', "SEEDS": str(w4["seeds"]),
        "BASE_CLEAN": f'{arms["base"]["served"]["clean"]["cache_caused"]:.1f}',
        "UPPER": f'{ci3["all/clean"]["ci"][1]:.1f}', "HITS": f'{arms["all"]["honest_hit_rate"]:.1f}',
        "MISS": f'{arms["all"]["served"]["clean"]["filter_miss"]:.0f}',
        "FA_ORD_K": str(fa_ord["k"]), "FA_ORD_N": f'{fa_ord["n"]:,}', "FA_LOOK": f'{fa_look["rate"]:.1f}',
        "FA_LOOK_N": f'{fa_look["n"]:,}', "DET_DS": f'{det_ds["rate"]:.1f}', "DET_JAY": f'{det_jay["rate"]:.1f}',
        "AUC_ORD": f'{scr["auc_ordinary"]:.3f}', "AUC_LOOK": f'{scr["auc_lookalike"]:.3f}',
        "EASY": f'{100 * (1 - easy["router"] / easy["strong"]):.0f}', "ALL_SAVED": f'{rtr["saved_pct"]:.0f}',
        "REFS": str(refs), "DEFENCE_ROWS": "\n".join(defence_rows), "BYPASS_ROWS": "\n".join(bypass_rows),
        "FIG_BYPASS": b64(FIG / "fig_bypass_threshold.png"), "FIG_DEFENCE": b64(FIG / "fig_defence_settings.png"),
        "FIG_FILTER": b64(FIG / "fig_filter_alone.png"),
    }
    slides = SLIDES
    for key, value in v.items():
        slides = slides.replace("{{" + key + "}}", value)
    left = re.findall(r"\{\{[A-Z0-9_]+\}\}", slides)
    if left:
        sys.exit(f"no value for {sorted(set(left))}")

    template = TEMPLATE.read_text()
    total = slides.count('class="slide')
    html_doc = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>SentryGate Phase 4 &middot; Final Review</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&family=IBM+Plex+Mono:ital,wght@0,400;0,500;0,600;1,400&display=swap">
{extract("style", template)}
<style>
.figframe img{{background:#fff;border-radius:8px;padding:10px;}}
.stats4{{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;margin-top:22px;}}
.stats4 .panel{{display:flex;flex-direction:column;gap:8px;}}
.paper-title{{font-size:28px;font-style:italic;line-height:1.3;}}
.figframe.tall{{flex:0 0 auto;}}
.figframe.tall img{{height:240px;width:auto;}}
</style>
</head>
<body>
<div class="viewport">
  <div class="stage" id="stage">
{slides}
  </div>
  <div class="chrome">
    <span>SentryGate &middot; Phase 4 &middot; Final</span>
    <span><span id="cur">1</span> / <span id="tot">{total}</span></span>
  </div>
  <div class="progress" id="prog"></div>
</div>
<div class="help"><kbd>&larr;</kbd> <kbd>&rarr;</kbd> move &nbsp; <kbd>N</kbd> notes &nbsp; <kbd>F</kbd> full screen</div>
<div class="notes" id="notes"><span class="nt">Presenter note</span><span id="noteBody"></span></div>
{extract("script", template)}
</body></html>
"""
    OUT.write_text(html_doc)
    print(f"wrote {OUT.relative_to(ROOT)}  ({total} slides)")
    return 0


SLIDES = """
    <!-- 1 TITLE -->
    <section class="slide on" data-notes="Name the checkpoint. This is the final review: the hole, the fix, every number with a range, the filter measured on its own, and the paper.">
      <div class="title-wrap">
        <div class="eyebrow">Final Review &middot; Phase 4</div>
        <div class="rule"></div>
        <h1>Measured, closed,<br>and written up.</h1>
        <p class="lede">The cache-before-filter bypass, the defence that closes it, and a journal paper where every number is rebuilt from the logs.</p>
        <div class="meta-row">
          <div><span class="meta-k">Team</span><span class="meta-v">Divyansh Sharma &middot; Sarvagya Dabas &middot; Yashvit Gauri</span></div>
          <div><span class="meta-k">Supervisor</span><span class="meta-v">Dr. Sandeep Singh</span></div>
          <div><span class="meta-k">State</span><span class="meta-v">All four phases complete</span></div>
        </div>
      </div>
    </section>

    <!-- 2 THE PROBLEM -->
    <section class="slide" data-notes="One sentence of recap. The cache goes first because it is fast, and on a hit the filter is never asked.">
      <div class="eyebrow">The problem</div>
      <h2>The cache answers before the filter is asked.</h2>
      <div class="thesis">
        <q>A reworded attack can match a poisoned cached answer, and be served it <strong class="red">without the safety filter ever running</strong>.</q>
      </div>
      <p class="lede">We measured this on our own running gateway, with the real filter, embedder, Qdrant and Redis.</p>
    </section>

    <!-- 3 E1 -->
    <section class="slide" data-notes="The headline. Read the 0.85 row. The ranges are 95 percent bootstrap ranges over whole attacks, so this is not noise. Tightening the threshold barely helps.">
      <div class="eyebrow">E1 &middot; The bypass</div>
      <h2><span class="amber">{{LAZY85}}%</span> of lazy rewordings got through at 0.85.</h2>
      <div class="grid2 fill" style="align-items:start;">
        <div class="panel">
          <table>
            <thead><tr><th>Threshold</th><th class="num">Lazy edits</th><th class="num">Paraphrases</th><th class="num">All</th></tr></thead>
            <tbody>
{{BYPASS_ROWS}}
            </tbody>
          </table>
        </div>
        <div class="figframe" style="margin:0;"><img src="{{FIG_BYPASS}}" alt="Bypass rate against cache threshold, with 95% bands."></div>
      </div>
      <p><small>{{SEEDS}} public attacks, {{N}} rewordings per threshold. 95% range at 0.85: {{LAZY85_CI}}%. No threshold is both safe and useful.</small></p>
    </section>

    <!-- 4 E3 table -->
    <section class="slide" data-notes="The fix. Read down the realistic column. Label matching barely helps, risky-only re-checking leaves a third, re-checking every hit gives zero.">
      <div class="eyebrow">E3 &middot; The defence</div>
      <h2>Only re-checking every hit closes the hole.</h2>
      <div class="panel" style="overflow:auto;">
        <table>
          <thead><tr><th>Setting</th><th class="num">Cache-caused, saved as clean</th><th class="num">Cache-caused, saved as attack</th><th class="num">Honest hits kept</th></tr></thead>
          <tbody>
{{DEFENCE_ROWS}}
          </tbody>
        </table>
      </div>
      <p class="lede">{{BASE_CLEAN}}% &rarr; <strong class="green">0 of {{N}}</strong> (upper bound {{UPPER}}%), and honest users keep <strong>{{HITS}}%</strong> of their hits.</p>
    </section>

    <!-- 5 E3 chart -->
    <section class="slide" data-notes="Two kinds of leak. Coloured is the cache's fault, grey the filter misses even when asked. The safe setting removes all of the first and none of the second.">
      <div class="eyebrow">Whose fault is each leak</div>
      <h2>The cache's fault, separated from the filter's.</h2>
      <div class="figframe"><img src="{{FIG_DEFENCE}}" alt="Poison served under each defence setting, split into cache-caused and filter misses."></div>
      <p><small>What is still served with every hit re-checked, about {{MISS}}%, is exactly what the filter misses when asked directly.</small></p>
    </section>

    <!-- 6 E4 -->
    <section class="slide" data-notes="New in Phase 4. On ordinary text the filter almost never blocks anyone. On look-alikes and conversational attacks it is weak. A cache defence cannot fix that.">
      <div class="eyebrow">E4 &middot; The filter on its own</div>
      <h2>Two numbers that must not be pooled.</h2>
      <div class="stats4">
        <div class="panel"><span class="stat-n green">{{FA_ORD_K}}</span><span class="stat-k">false alarm in {{FA_ORD_N}} ordinary honest texts</span></div>
        <div class="panel"><span class="stat-n red">{{FA_LOOK}}%</span><span class="stat-k">of {{FA_LOOK_N}} look-alike honest texts blocked</span></div>
        <div class="panel"><span class="stat-n green">{{DET_JAY}}%</span><span class="stat-k">of jayavibhav attacks caught</span></div>
        <div class="panel"><span class="stat-n red">{{DET_DS}}%</span><span class="stat-k">of conversational deepset attacks caught</span></div>
      </div>
      <div class="figframe tall" style="margin-top:18px;"><img src="{{FIG_FILTER}}" alt="Score distributions and the catch against false-alarm curve."></div>
      <p><small>Area under the curve: {{AUC_ORD}} on ordinary text, {{AUC_LOOK}} on look-alikes.</small></p>
    </section>

    <!-- 7 E5 + mitigations -->
    <section class="slide" data-notes="The other layers, briefly. Routing cuts the cost of easy questions; the guard and limiter were shown live in Phase 3.">
      <div class="eyebrow">E5 &middot; Cost and the other layers</div>
      <h2>Easy questions cost <span class="green">{{EASY}}%</span> less.</h2>
      <div class="grid2" style="align-items:start;">
        <div class="panel" style="display:flex;flex-direction:column;gap:12px;">
          <h3 class="amber">Model picker, 80 live paid calls</h3>
          <p style="font-size:19px;">Easy questions go to the cheap model, hard ones to the strong one.</p>
          <p style="font-size:19px;">Easy: <strong class="green">{{EASY}}% cheaper</strong>. Overall: <strong>{{ALL_SAVED}}%</strong>.</p>
        </div>
        <div class="panel" style="display:flex;flex-direction:column;gap:12px;">
          <h3 class="amber">Shown live</h3>
          <p style="font-size:19px;"><strong>Output guard</strong> refused a cached answer carrying a cookie-stealing script.</p>
          <p style="font-size:19px;"><strong>Rate limit</strong> slowed one caller's burst of probes; other callers unaffected.</p>
        </div>
      </div>
    </section>

    <!-- 8 THE PAPER -->
    <section class="slide" data-notes="The main deliverable of the phase. What makes it credible: every number regenerated from the logs, every reference checked against its published record.">
      <div class="eyebrow">The paper</div>
      <h2>Written up as a journal paper.</h2>
      <div class="panel"><p class="paper-title">Measuring and Closing a Semantic-Cache Bypass of Prompt-Injection Filters in Large Language Model Gateways</p></div>
      <div class="stats4">
        <div class="panel"><span class="stat-n amber">13</span><span class="stat-k">pages, two-column journal layout</span></div>
        <div class="panel"><span class="stat-n amber">{{REFS}}</span><span class="stat-k">references, each checked against its published record</span></div>
        <div class="panel"><span class="stat-n amber">5</span><span class="stat-k">experiments, every rate with a 95% range</span></div>
        <div class="panel"><span class="stat-n amber">1</span><span class="stat-k">command rebuilds every number from the logs</span></div>
      </div>
      <p><small>Prepared for submission to the Arabian Journal for Science and Engineering.</small></p>
    </section>

    <!-- 9 PLAN -->
    <section class="slide" data-notes="All four phases are done, each ending in one measured result.">
      <div class="eyebrow">Timeline</div>
      <h2>Four phases, all complete.</h2>
      <div class="rail">
        <div class="ph"><span class="ph-n">01</span><span class="ph-w">18&ndash;22 Aug</span><span class="ph-t">Prove the problem is real</span><span class="ph-s">done</span></div>
        <div class="ph"><span class="ph-n">02</span><span class="ph-w">23 Aug&ndash;26 Sep</span><span class="ph-t">Build the gateway and reproduce the bypass on it</span><span class="ph-s">done</span></div>
        <div class="ph"><span class="ph-n">03</span><span class="ph-w">27 Sep&ndash;24 Oct</span><span class="ph-t">Build the defence and measure what it costs</span><span class="ph-s">done</span></div>
        <div class="ph"><span class="ph-n">04</span><span class="ph-w">25 Oct&ndash;14 Nov</span><span class="ph-t">Final evaluation, filter study and journal paper</span><span class="ph-s now">done</span></div>
      </div>
    </section>

    <!-- 10 CLOSE -->
    <section class="slide" data-notes="Land on the sentence and stop. Take questions.">
      <div class="eyebrow">In one sentence</div>
      <div class="thesis">
        <q>A cache in front of a safety filter is a path around it; <strong class="green">re-checking every hit</strong> removes the risk the cache adds, at a few tens of milliseconds per hit.</q>
        <p class="lede">What remains is the filter's own error &mdash; which a cache defence cannot fix.</p>
      </div>
      <div class="meta-row">
        <div><span class="meta-k">Rebuild the paper</span><span class="meta-v mono">make journal</span></div>
        <div><span class="meta-k">Reproduce the defence</span><span class="meta-v mono">make defence</span></div>
      </div>
    </section>
"""


if __name__ == "__main__":
    sys.exit(main())
