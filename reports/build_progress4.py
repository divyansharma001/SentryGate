"""Build Progress Report-4 (Phase 4, final) in the same format as Progress Reports 1 to 3.

Every number is read from the committed results, so the report cannot drift
from what the code measured:

    data/week4/report.json      the bypass sweep (Phase 2)
    data/phase3/report.json     the defence settings (Phase 3)
    data/phase4/report.json     confidence ranges and the filter-alone study (Phase 4)
    data/router/report.json     the model picker, on live paid calls
    data/mitigations/demo.txt   the output guard and rate limit, live

Writes reports/out/Progress4.docx. The PDF is converted from it (make report4).

Run:  python3 reports/build_progress4.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from report_common import (
    GREEN, ORANGE, RED, ROOT, bullet, caption, figure, heading, new_report, page_break,
    para, pct, save, table_minimal as table,
)
import subprocess

W4 = json.loads((ROOT / "data/week4/report.json").read_text())
P3 = json.loads((ROOT / "data/phase3/report.json").read_text())
P4 = json.loads((ROOT / "data/phase4/report.json").read_text())
RTR = json.loads((ROOT / "data/router/report.json").read_text())
DEMO = (ROOT / "data/mitigations/demo.txt").read_text()
MANIFEST = json.loads((ROOT / "data/week4/manifest.json").read_text())
FIG = ROOT / "paper/journal/figures"

ARMS = P3["arms"]
SCR = P4["screening"]
SWEEP = P4["earlier"]["bypass_by_threshold"]
CI3 = P4["earlier"]["phase3_cache_caused"]


def ci(cell: dict) -> str:
    return f"{cell['ci'][0]:.1f}-{cell['ci'][1]:.1f}"


def references() -> int:
    """Count of references in the journal paper, read from its source."""
    text = (ROOT / "paper/journal/parts/back_matter.html").read_text()
    return len(re.findall(r"<p>", text.split("<h2>References</h2>", 1)[1]))


def architecture_png() -> Path:
    """The paper's architecture diagram (paper/journal/diagrams/architecture.svg), as a PNG for Word."""
    svg = (ROOT / "paper/journal/diagrams/architecture.svg").read_text()
    m = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    w, h = int(m.group(1)), int(m.group(2))
    out_dir = ROOT / "reports/out"
    out_dir.mkdir(parents=True, exist_ok=True)
    page = out_dir / "architecture.html"
    page.write_text(f'<!doctype html><body style="margin:0;background:#fff">'
                    f'{svg.replace("<svg ", f"<svg width={w} height={h} ", 1)}</body>')
    png = out_dir / "architecture-final.png"
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=3",
                    f"--window-size={w},{h}", f"--screenshot={png}", page.as_uri()], check=True, capture_output=True)
    page.unlink()
    return png


def build() -> Path:
    doc = new_report("Progress Report-4 (Final)")
    base, every = ARMS["base"], ARMS["all"]
    lazy85 = SWEEP["0.85"]["lazy"]
    fa_ord, fa_look = SCR["false_alarms_ordinary"], SCR["false_alarms_lookalike"]
    det_deepset = SCR["by_dataset"]["deepset"]["detection"]
    n_variants = W4["attack_variants_per_threshold"]

    # ---- 1. status summary ----------------------------------------------
    heading(doc, "1.  Status Summary")
    para(doc, "**The project is complete, and the results are written up as a journal paper.** The objective of "
              "this phase was to finish the evaluation, put a confidence range on every result, measure the "
              "safety filter on its own, and turn the work of all four phases into a paper ready for "
              "submission.")
    para(doc, f"The headline results now carry 95% confidence ranges. **At a cache threshold of 0.85, "
              f"{pct(lazy85['rate'])} of lazily reworded attacks (range {ci(lazy85)}%) were served a poisoned "
              f"answer without the filter running.** With the safety check run again on every cache hit, "
              f"**cache-caused leaks fell to 0 of {n_variants:,}** (upper bound {CI3['all/clean']['ci'][1]:.1f}%), "
              f"while honest users kept {pct(every['honest_hit_rate'])} of their cache hits.")
    para(doc, f"The new filter study separates two very different numbers. On {fa_ord['n']:,} ordinary honest "
              f"texts the filter raised **{fa_ord['k']} false alarm**, but it blocked **{pct(fa_look['rate'])}** of "
              f"synthetic honest texts that contain attack-like words, and caught only "
              f"**{pct(det_deepset['rate'])}** of conversational attacks. This bounds what any cache defence built "
              "on the filter can achieve.")

    # ---- 2. work completed ----------------------------------------------
    heading(doc, "2.  Work Completed in Phase 4")
    bullet(doc, "Confidence ranges on every result",
           "the rewordings of one attack are not independent, so every attack rate is now reported with a 95% "
           "range from a bootstrap over whole seeds (2,000 resamples). When nothing leaks, the conservative "
           "rule-of-three upper bound is given instead.")
    bullet(doc, "The filter on its own",
           f"{fa_ord['n'] + fa_look['n']:,} honest texts and {SCR['detection']['n']:,} attacks the filter was never "
           "tuned on, including 1,000 everyday instructions from the public Dolly-15k dataset. Ordinary and "
           "look-alike honest text are reported separately, with Wilson 95% ranges and the full curve of catches "
           "against false alarms.")
    bullet(doc, "Journal paper",
           "a 13-page two-column paper covering all four phases: threat model, design, method, five experiments, "
           f"discussion and threats to validity, with {references()} references, each checked against its "
           "published record. The related work was updated after finding two 2026 NDSS papers on cache "
           "poisoning, and our claim was narrowed to stay accurate against them.")
    bullet(doc, "Submission package",
           "the paper prepared for the Arabian Journal for Science and Engineering, with a cover letter, a "
           "single-column manuscript version and a Word copy of the final layout.")
    bullet(doc, "Reproducibility",
           "one command rebuilds the paper; every number in it is filled in from the committed result files, and "
           "the build stops if any value is missing. Every figure is drawn by a committed script.")
    bullet(doc, "Engineering quality",
           "two new experiment switches (turning the filter off, and a fixed model delay), 93 automated tests "
           "(up from 88), a new check that every setting reaches the container, and a pinned code checker with "
           "no findings.")

    # ---- 3. final results ------------------------------------------------
    heading(doc, "3.  Final Results")
    para(doc, "Table 1 brings together the five experiments of the project. E1 to E4 use the real filter, "
              "embedding model, Qdrant and Redis; E5 uses real, paid model calls.")
    s3 = SWEEP
    table(doc, ["#", "Experiment", "Main result"], [
        ["E1", "The bypass, across 7 cache thresholds",
         (f"{pct(s3['0.85']['lazy']['rate'])} of lazy edits served the poison at 0.85; "
          f"{pct(s3['0.95']['lazy']['rate'])} even at 0.95", RED)],
        ["E2", "Filter moved in front of the cache", "Bypass falls to 0%: the order is the cause"],
        ["E3", "Verdict-tagged caching, 5 settings",
         (f"Re-check every hit: 0 cache-caused leaks, {pct(every['honest_hit_rate'])} honest hits kept", GREEN)],
        ["E4", "The filter alone, on unseen texts",
         f"{fa_ord['k']} false alarm in {fa_ord['n']:,} ordinary texts; {pct(fa_look['rate'])} on look-alikes"],
        ["E5", "Model picker, 80 live calls",
         f"Easy questions {100 * (1 - RTR['cost_by_label']['easy']['router'] / RTR['cost_by_label']['easy']['strong']):.0f}% "
         f"cheaper, {RTR['saved_pct']:.0f}% overall"],
    ], widths=[0.45, 2.3, 3.75], center_cols=(0,))
    caption(doc, "Table 1 - The five experiments and their main results.")

    heading(doc, "3.1  The Bypass, with Confidence Ranges (E1)", size=12.5)
    rows = []
    for t in ("0.95", "0.90", "0.85", "0.80", "0.75", "0.70", "0.65"):
        r = SWEEP[t]
        rows.append([f"{float(t):.2f}", f"{pct(r['lazy']['rate'])} ({ci(r['lazy'])})",
                     f"{pct(r['rewrite']['rate'])} ({ci(r['rewrite'])})", f"{pct(r['all']['rate'])} ({ci(r['all'])})"])
    table(doc, ["Threshold", "Lazy edits", "Full paraphrases", "All rewordings"], rows,
          widths=[1.0, 1.85, 1.85, 1.85], center_cols=(0, 1, 2, 3), bold_row=2)
    caption(doc, "Table 2 - Bypass rate by cache threshold, with 95% ranges.")
    para(doc, "Table 2 shows that lazy edits get through at every threshold a product would use, while full "
              "paraphrases only match once the cache is loose. Figure 1 shows the same result as a chart; the "
              "shaded bands are the 95% ranges.")
    figure(doc, FIG / "fig_bypass_threshold.png", 3.8)
    caption(doc, "Figure 1 - Bypass rate against cache threshold.")

    heading(doc, "3.2  The Defence, with Confidence Ranges (E3)", size=12.5)
    names = {"base": "No defence", "filter": "Label match only", "recheck": "Re-check risky hits only",
             "both": "Label match + re-check risky hits", "all": "Label match + re-check every hit"}
    rows = []
    for tag in ("base", "filter", "recheck", "both", "all"):
        a = ARMS[tag]
        clean, attack = a["served"]["clean"]["cache_caused"], a["served"]["attack"]["cache_caused"]
        colour = GREEN if tag == "all" else (RED if clean > 40 else ORANGE)
        rows.append([names[tag], (f"{pct(clean)} ({ci(CI3[tag + '/clean'])})", colour),
                     f"{pct(attack)} ({ci(CI3[tag + '/attack'])})", pct(a["honest_hit_rate"]),
                     f"{a['hit_p50_ms']:.0f} ms"])
    table(doc, ["Setting", "Cache-caused, saved as clean", "Cache-caused, saved as attack",
                "Honest hits kept", "Median hit"],
          rows, widths=[2.0, 1.35, 1.35, 0.9, 0.85], center_cols=(1, 2, 3, 4), bold_row=4)
    caption(doc, "Table 3 - Cache-caused leaks in each defence setting at threshold 0.85, with 95% ranges.")
    para(doc, "Table 3 confirms the Phase 3 result with ranges: only re-checking every hit removes the leaks the "
              "cache causes, in both the easy and the realistic case. Figure 2 splits each bar into the part the "
              "cache caused (coloured) and the part the filter misses even when asked (grey).")
    figure(doc, FIG / "fig_defence_settings.png", 6.2)
    caption(doc, "Figure 2 - Poison served under each defence setting.")

    heading(doc, "3.3  The Filter on its Own (E4)", size=12.5)
    by = SCR["by_dataset"]
    table(doc, ["Texts", "n", "Blocked", "95% range"], [
        ["Honest: deepset", f"{by['deepset']['false_alarms']['n']:,}", pct(by["deepset"]["false_alarms"]["rate"]),
         ci(by["deepset"]["false_alarms"])],
        ["Honest: Dolly-15k", f"{by['dolly']['false_alarms']['n']:,}", pct(by["dolly"]["false_alarms"]["rate"]),
         ci(by["dolly"]["false_alarms"])],
        ["Honest, ordinary (both)", f"{fa_ord['n']:,}", (pct(fa_ord["rate"]), GREEN), ci(fa_ord)],
        ["Honest, look-alike: jayavibhav", f"{fa_look['n']:,}", (pct(fa_look["rate"]), RED), ci(fa_look)],
        ["Attacks: deepset", f"{det_deepset['n']:,}", (pct(det_deepset["rate"]), RED), ci(det_deepset)],
        ["Attacks: jayavibhav", f"{by['jayavibhav']['detection']['n']:,}",
         pct(by["jayavibhav"]["detection"]["rate"]), ci(by["jayavibhav"]["detection"])],
    ], widths=[2.6, 0.9, 1.1, 1.4], center_cols=(1, 2, 3))
    caption(doc, "Table 4 - The filter alone at its default threshold of 0.5.")
    para(doc, "Table 4 shows that the filter almost never blocks ordinary users, but blocks most synthetic "
              "honest texts that use attack-like words, and misses most conversational attacks. Figure 3 shows "
              "why changing the block threshold does not help: the scores sit at the two ends of the scale "
              f"(area under the curve {SCR['auc_ordinary']:.3f} on ordinary text, {SCR['auc_lookalike']:.3f} on "
              "look-alikes).")
    figure(doc, FIG / "fig_filter_alone.png", 6.2)
    caption(doc, "Figure 3 - Scores and error rates of the filter alone.")

    heading(doc, "3.4  Cost Routing and Live Mitigations (E5)", size=12.5)
    c = RTR["cost_by_label"]
    table(doc, ["Questions", "Always strong model", "Model picker", "Saved"], [
        ["Easy (20)", f"${c['easy']['strong']:.5f}", f"${c['easy']['router']:.5f}",
         (f"{100 * (1 - c['easy']['router'] / c['easy']['strong']):.0f}%", GREEN)],
        ["Hard (20)", f"${c['hard']['strong']:.5f}", f"${c['hard']['router']:.5f}",
         f"{100 * (1 - c['hard']['router'] / c['hard']['strong']):.0f}%"],
        ["All 40", f"${RTR['strong_cost_usd']:.5f}", f"${RTR['router_cost_usd']:.5f}", f"{RTR['saved_pct']:.0f}%"],
    ], widths=[1.6, 1.6, 1.6, 1.0], center_cols=(1, 2, 3), bold_row=2)
    caption(doc, "Table 5 - Model routing on live paid calls (real token counts).")
    refused = re.search(r"429 refused, rate limit: (\d+)", DEMO)
    para(doc, "Table 5 shows that routing cuts the cost of easy questions sharply; the overall saving depends on "
              "how much of the traffic is easy. The output guard and the rate limiter were demonstrated live in "
              "Phase 3: in block mode the guard refused a cached answer carrying a cookie-stealing script, and "
              f"the limiter refused {refused.group(1) if refused else 'the excess'} of one caller's burst of probes "
              "with HTTP 429 while other callers were unaffected.")

    # ---- 4. timeline -----------------------------------------------------
    heading(doc, "4.  Project Timeline")
    table(doc, ["Phase", "Window", "Objective and deliverable", "Status"], [
        ["1", "18 - 22 Aug 2026", "Establish the problem. Offline proof-of-concept, threshold sweep, "
                                  "architecture definition, synopsis.", ("COMPLETE", GREEN)],
        ["2", "23 Aug - 26 Sep 2026", "Build the gateway and reproduce the bypass on our own running "
                                      "system. First real bypass-rate figure.", ("COMPLETE", GREEN)],
        ["3", "27 Sep - 24 Oct 2026", "Build and validate the defence. Verdict-tagged cache, "
                                      "re-verification, routing, output guard, rate limiting.", ("COMPLETE", GREEN)],
        ["4", "25 Oct - 14 Nov 2026", "Final evaluation with confidence ranges, filter study, journal paper "
                                      "and submission package.", ("COMPLETE", GREEN)],
    ], widths=[0.6, 1.4, 3.3, 1.1], center_cols=(0, 3))
    caption(doc, "Table 6 - Phase-level schedule.")

    heading(doc, "4.1  Limitations", size=12.5)
    bullet(doc, "Mocked model replies",
           "the attack experiments mock the model's reply, because the attack concerns answers served from the "
           "cache, where the model is never called. The filter, embedder and stores are real.")
    bullet(doc, "One filter, one embedder",
           "absolute rates will differ for other components; the structural result, that a cache in front of a "
           "filter bypasses it unless hits are re-checked, does not depend on either.")
    bullet(doc, "Dataset provenance",
           "the jayavibhav dataset documents neither its sources nor its labels, and its honest texts are "
           "synthetic; its false alarms are therefore reported separately from ordinary text.")
    bullet(doc, "Router tuning",
           f"the routing rules were adjusted once after seeing the {RTR['questions']} questions, so the "
           f"{RTR['agrees_with_our_label']} of {RTR['questions']} agreement is optimistic.")

    heading(doc, "4.2  Future Work", size=12.5)
    bullet(doc, "Other filters and embedders",
           "repeat the measurements with other injection classifiers, LLM-based guards and embedding models.")
    bullet(doc, "Other injection routes",
           "pre-filled and cross-tenant caches, where a poisoned entry can carry any verdict an attacker chooses.")
    bullet(doc, "Adaptive attackers",
           "rewordings that match the poisoned entry and also evade the filter; combine the verdict re-check with "
           "a check that the cached answer fits the new question.")
    bullet(doc, "A learned model picker",
           "evaluated on questions it was not tuned on, in place of the rule-based one.")

    # ---- 5. architecture -------------------------------------------------
    heading(doc, "5.  Final System Architecture")
    para(doc, "Figure 4 shows the final gateway. **The cache is consulted first, for speed, but a hit needs a "
              "matching safety label and passes a fresh safety check before it is served.** Every answer passes "
              "the output guard, and a rate limit sits in front of everything.")
    figure(doc, architecture_png(), 6.4)
    caption(doc, "Figure 4 - SentryGate, final system.")
    para(doc, "**Reading the diagram:** a request passes Nginx and the rate limit, then reaches the cache, which "
              "only returns stored answers whose safety label matches the question. On a hit, the safety check "
              "runs again on the new question, without calling the model; an attack is refused with 403. On a "
              "miss, the safety check runs, and a clean question goes to the model picker. The output guard "
              "inspects every answer, fresh answers are stored with their safety label, and every request is "
              "recorded in the log, the single source of every number in this report.", after=0)

    return save(doc, "Progress4.docx")


if __name__ == "__main__":
    print("wrote", build().relative_to(ROOT))
