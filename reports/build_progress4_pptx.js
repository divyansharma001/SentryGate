/*
 * Build reports/out/SentryGate_Progress_Report_4.pptx, for the final review on 14 November.
 *
 * Same design and structure as Progress Reports 2 and 3 (reports/deck_common.js),
 * filled with Phase 4: the final results with confidence ranges, the filter on
 * its own, and the journal paper.
 *
 * Numbers are read from the committed results:
 *   data/week4/report.json, data/phase3/report.json, data/phase4/report.json,
 *   data/router/report.json, data/mitigations/demo.txt
 *
 * Run:  make report4-pptx
 */

const fs = require("fs");
const path = require("path");
const { C, makeDeck } = require("./deck_common");

const ROOT = path.join(__dirname, "..");
const read = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf8"));
const W4 = read("data/week4/report.json");
const P3 = read("data/phase3/report.json");
const P4 = read("data/phase4/report.json");
const RTR = read("data/router/report.json");
const DEMO = fs.readFileSync(path.join(ROOT, "data/mitigations/demo.txt"), "utf8");
const A = P3.arms;
const SCR = P4.screening;
const SW = P4.earlier.bypass_by_threshold;
const CI3 = P4.earlier.phase3_cache_caused;
const FIG = path.join(ROOT, "paper/journal/figures");
const BACK = fs.readFileSync(path.join(ROOT, "paper/journal/parts/back_matter.html"), "utf8");
const REFS = (BACK.split("<h2>References</h2>")[1].match(/<p>/g) || []).length;

const { NAVY, GOLD, RED, GREEN, BLUE, SLATE, TEXT, MUTED, LINE, ALT, WHITE, FONT, W, MX, CREAM } = C;
const TOTAL = 13;

const D = makeDeck("SentryGate · Progress Report 4 (Final)");
const { pres, slide, label, title, sub, card, pill } = D;

const p1 = (x) => `${x.toFixed(1)}%`;
const p0 = (x) => `${x.toFixed(0)}%`;
const ci = (c) => `${c.ci[0].toFixed(1)}–${c.ci[1].toFixed(1)}`;
const N = W4.attack_variants_per_threshold;
const FA_ORD = SCR.false_alarms_ordinary, FA_LOOK = SCR.false_alarms_lookalike;
const DET_DS = SCR.by_dataset.deepset.detection, DET_JAY = SCR.by_dataset.jayavibhav.detection;
const EASY_SAVED = Math.round(100 * (1 - RTR.cost_by_label.easy.router / RTR.cost_by_label.easy.strong));
const REFUSED = (DEMO.match(/429 refused, rate limit: (\d+)/) || [0, "?"])[1];
// PNG figures are 300 dpi; keep their real aspect ratio.
function img(file) {
  const b = fs.readFileSync(path.join(FIG, file));
  return { path: path.join(FIG, file), ratio: b.readUInt32BE(20) / b.readUInt32BE(16) };
}

// ---- 01 cover ---------------------------------------------------------------
(() => {
  const s = slide("Name the checkpoint. This is the final review: the full results with confidence ranges, the filter measured on its own, and the paper.");
  s.addText("PROJECT PROGRESS REPORT · DEPARTMENT OF INFORMATION TECHNOLOGY", { x: MX, y: 0.62, w: 11, h: 0.3,
    isTextBox: true, margin: 0, fontFace: FONT, fontSize: 12.5, color: GOLD });
  s.addText("SentryGate", { x: MX, y: 2.35, w: 9, h: 1.05, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 62, color: NAVY });
  s.addText("A Security-Aware Semantic Caching Gateway for Large Language Model Applications", { x: MX, y: 3.45, w: 11.5, h: 0.5,
    isTextBox: true, margin: 0, fontFace: FONT, fontSize: 20, italic: true, color: MUTED });
  s.addShape(pres.ShapeType.line, { x: MX - 0.08, y: 4.15, w: 3.0, h: 0, line: { color: GOLD, width: 1 } });
  s.addText("PROGRESS REPORT — 4 (FINAL)", { x: MX, y: 4.38, w: 7, h: 0.35, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 15, color: NAVY });
  const meta = [["TEAM", "Divyansh Sharma · Sarvagya Dabas · Yashvit Gauri"],
                ["PROGRAMME", "B.Tech Information Technology, Batch 2023–27"],
                ["SUPERVISOR", "Dr. Sandeep Singh"]];
  meta.forEach(([k, v], i) => {
    const y = 4.88 + i * 0.66;
    s.addText(k, { x: MX, y, w: 5, h: 0.24, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 11, color: GOLD });
    s.addText(v, { x: MX, y: y + 0.25, w: 8, h: 0.32, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 15, color: NAVY });
  });
  s.addText("Maharaja Surajmal Institute of Technology, New Delhi", { x: MX, y: 6.98, w: 8, h: 0.28, isTextBox: true, margin: 0,
    fontFace: FONT, fontSize: 11, color: MUTED });
})();

// ---- 02 status summary -------------------------------------------------------
(() => {
  const s = slide("Lead with the result. The hole is real, the fix closes it, and every number now has a confidence range. The paper is ready to submit.");
  label(s, "// 01 — Status Summary");
  title(s, "Complete, measured, and written up");
  s.addText("The objective was to finish the evaluation, put a range on every result, measure the filter on its own, and write the paper.",
    { x: MX, y: 1.8, w: 7.3, h: 0.9, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 15.5, italic: true, color: MUTED, lineSpacingMultiple: 1.25, valign: "top" });
  s.addText([
    { text: `At a cache threshold of 0.85, ${p1(SW["0.85"].lazy.rate)} of lazily reworded attacks were served a poisoned answer, and the filter never ran. `, options: { color: TEXT } },
    { text: `Re-checking every cache hit cut the leaks the cache causes to 0 of ${N.toLocaleString()}`, options: { color: TEXT, bold: true } },
    { text: `, and honest users kept ${p1(A.all.honest_hit_rate)} of their hits.`, options: { color: TEXT } },
  ], { x: MX, y: 2.85, w: 7.3, h: 2.0, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 16.5, lineSpacingMultiple: 1.35, valign: "top" });

  const cx = 8.35, cw = 4.35;
  card(s, cx, 1.6, cw, 4.6);
  s.addText("CACHE-CAUSED LEAKS", { x: cx + 0.4, y: 1.92, w: 3.5, h: 0.26, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 11, color: GOLD });
  s.addText(p1(A.base.served.clean.cache_caused), { x: cx + 0.4, y: 2.2, w: 1.9, h: 0.8, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 40, color: RED });
  s.addText("→", { x: cx + 2.05, y: 2.2, w: 0.4, h: 0.8, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 28, color: MUTED, align: "center", valign: "middle" });
  s.addText("0.0%", { x: cx + 2.5, y: 2.2, w: 1.6, h: 0.8, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 40, color: GREEN });
  s.addText(`no defence → re-check every hit (95% upper bound ${CI3["all/clean"].ci[1].toFixed(1)}%)`,
    { x: cx + 0.4, y: 3.0, w: 3.6, h: 0.6, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 11.5, color: MUTED, lineSpacingMultiple: 1.1, valign: "top" });
  s.addShape(pres.ShapeType.line, { x: cx + 0.3, y: 3.75, w: cw - 0.6, h: 0, line: { color: LINE, width: 1 } });
  s.addText(`${FA_ORD.k} in ${FA_ORD.n.toLocaleString()}`, { x: cx + 0.4, y: 3.9, w: 3.6, h: 0.8, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 36, color: GREEN });
  s.addText("false alarms on ordinary honest text",
    { x: cx + 0.4, y: 4.7, w: 3.6, h: 0.5, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 11.5, color: MUTED, valign: "top" });
  s.addShape(pres.ShapeType.line, { x: cx + 0.3, y: 5.3, w: cw - 0.6, h: 0, line: { color: LINE, width: 1 } });
  s.addText([
    { text: `Journal paper, ${REFS} verified references. `, options: { color: TEXT } },
    { text: "Ready to submit.", options: { color: GREEN, italic: true } },
  ], { x: cx + 0.4, y: 5.42, w: 3.7, h: 0.55, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 13, valign: "top" });
})();

// ---- 03 work completed --------------------------------------------------------
(() => {
  const s = slide("Six workstreams, one per card. The two that matter most are the confidence ranges and the filter study, because they make every claim defensible.");
  label(s, "// 02 — Work Completed");
  title(s, "Six workstreams closed in Phase 4");
  const items = [
    ["Confidence ranges", "Every attack rate now has a 95% range from a bootstrap over whole seeds; a zero gets a rule-of-three upper bound."],
    ["The filter on its own", `${(FA_ORD.n + FA_LOOK.n).toLocaleString()} honest texts and ${SCR.detection.n.toLocaleString()} attacks it was never tuned on, including 1,000 everyday Dolly-15k instructions.`],
    ["Journal paper", `13 pages, two columns, five experiments, ${REFS} references each checked against its published record.`],
    ["Related-work check", "Found two 2026 NDSS papers on cache poisoning; our claim was narrowed so it stays accurate."],
    ["Submission package", "Prepared for the Arabian Journal for Science and Engineering, with a cover letter and a manuscript version."],
    ["Reproducibility & quality", "One command rebuilds the paper from the result files. 93 tests, up from 88; code checker clean."],
  ];
  const gx = 0.2, x0 = 0.6, cw = (12.1 - 2 * gx) / 3, ch = 2.3, gy = 0.25, y0 = 1.85;
  items.forEach(([h, b], i) => {
    const x = x0 + (i % 3) * (cw + gx), y = y0 + Math.floor(i / 3) * (ch + gy);
    card(s, x, y, cw, ch);
    s.addText(String(i + 1).padStart(2, "0"), { x: x + 0.35, y: y + 0.25, w: 1, h: 0.45, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 24, color: GOLD });
    s.addText(h, { x: x + 0.35, y: y + 0.82, w: cw - 0.6, h: 0.35, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 15, color: NAVY });
    s.addText(b, { x: x + 0.35, y: y + 1.28, w: cw - 0.6, h: 0.9, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 11.5, color: MUTED, lineSpacingMultiple: 1.12, valign: "top" });
  });
})();

// ---- 04 five experiments ------------------------------------------------------
(() => {
  const s = slide("The whole project on one slide. Five experiments, each with one result. E1 shows the hole, E2 its cause, E3 the fix, E4 the filter's own limit, E5 the cost saving.");
  label(s, "// 03 — The Five Experiments");
  title(s, "The whole project in five results");
  const rows = [
    ["E1", "The bypass, 7 thresholds", `${p1(SW["0.85"].lazy.rate)} of lazy edits served the poison at 0.85`, RED],
    ["E2", "Filter moved before the cache", "Bypass falls to 0%: the order is the cause", NAVY],
    ["E3", "Verdict-tagged caching, 5 settings", `Re-check every hit: 0 cache-caused leaks, ${p1(A.all.honest_hit_rate)} hits kept`, GREEN],
    ["E4", "The filter alone, unseen texts", `${FA_ORD.k} false alarm in ${FA_ORD.n.toLocaleString()} ordinary; ${p1(FA_LOOK.rate)} on look-alikes`, GOLD],
    ["E5", "Model picker, 80 live calls", `Easy questions ${EASY_SAVED}% cheaper, ${p0(RTR.saved_pct)} overall`, GREEN],
  ];
  rows.forEach(([id, what, res, col], i) => {
    const y = 1.9 + i * 0.95;
    card(s, 0.6, y, 12.1, 0.8, i % 2 ? ALT : WHITE);
    s.addText(id, { x: 0.85, y, w: 0.8, h: 0.8, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 20, color: GOLD, valign: "middle" });
    s.addText(what, { x: 1.75, y, w: 4.3, h: 0.8, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 15, color: NAVY, valign: "middle" });
    s.addText(res, { x: 6.1, y, w: 6.4, h: 0.8, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 15, color: col, bold: true, valign: "middle" });
  });
})();

// ---- 05 E1 chart ----------------------------------------------------------------
(() => {
  const s = slide("Read the 0.85 point: 97 percent of lazy edits get through. The bands are 95 percent ranges, so this is not noise. Tightening to 0.95 barely helps.");
  label(s, "// 04 — The Bypass, with Ranges");
  title(s, "No threshold is both safe and useful");
  const f = img("fig_bypass_threshold.png");
  const h = 4.7, w = h / f.ratio;
  s.addImage({ path: f.path, x: 0.6, y: 1.85, w, h });
  const cx = 8.35, cw = 4.35;
  card(s, cx, 1.85, cw, 4.7);
  s.addText("AT THRESHOLD 0.85", { x: cx + 0.4, y: 2.15, w: 3.5, h: 0.26, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 11, color: GOLD });
  [["Lazy edits", SW["0.85"].lazy, RED], ["Full paraphrases", SW["0.85"].rewrite, NAVY], ["All rewordings", SW["0.85"].all, NAVY]].forEach(([k, c, col], i) => {
    const y = 2.55 + i * 1.15;
    s.addText(p1(c.rate), { x: cx + 0.4, y, w: 3.6, h: 0.6, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 30, color: col });
    s.addText(`${k} · range ${ci(c)}%`, { x: cx + 0.4, y: y + 0.6, w: 3.6, h: 0.3, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 11.5, color: MUTED });
  });
})();

// ---- 06 E3 table ------------------------------------------------------------------
(() => {
  const s = slide("Same table as Phase 3, now with ranges. Only the last row reaches zero, in both the easy and the realistic case.");
  label(s, "// 05 — The Defence, with Ranges");
  title(s, "Only re-checking every hit closes the hole");
  sub(s, "Cache-caused = poison served on a text the filter blocks when asked directly. Threshold 0.85.");
  const NAMES = { base: "No defence", filter: "Label match only", recheck: "Re-check risky hits only",
                  both: "Label match + re-check risky hits", all: "Label match + re-check every hit" };
  const cols = [{ h: "Setting", x: 0.9, w: 4.0 }, { h: "Saved as clean (realistic)", x: 4.9, w: 2.5 },
                { h: "Saved as attack (easy)", x: 7.4, w: 2.4 }, { h: "Honest hits kept", x: 9.8, w: 1.6 }, { h: "Median hit", x: 11.4, w: 1.2 }];
  cols.forEach((c, i) => s.addText(c.h.toUpperCase(), { x: c.x, y: 2.3, w: c.w, h: 0.3, isTextBox: true, margin: 0,
    fontFace: FONT, fontSize: 10, color: GOLD, align: i ? "center" : "left" }));
  ["base", "filter", "recheck", "both", "all"].forEach((tag, i) => {
    const a = A[tag], y = 2.7 + i * 0.8, last = tag === "all";
    card(s, 0.6, y, 12.1, 0.68, last ? "EEF5EF" : (i % 2 ? ALT : WHITE), last ? GREEN : LINE);
    const clean = a.served.clean.cache_caused, att = a.served.attack.cache_caused;
    const vals = [NAMES[tag], `${p1(clean)}  (${ci(CI3[tag + "/clean"])})`, `${p1(att)}  (${ci(CI3[tag + "/attack"])})`,
                  p1(a.honest_hit_rate), `${Math.round(a.hit_p50_ms)} ms`];
    const colours = [NAVY, last ? GREEN : (clean > 40 ? RED : GOLD), att < 5 ? GREEN : RED, TEXT, last ? GOLD : TEXT];
    vals.forEach((v, j) => s.addText(v, { x: cols[j].x, y, w: cols[j].w, h: 0.68, isTextBox: true, margin: 0, fontFace: FONT,
      fontSize: j ? (j < 3 ? 14 : 15) : 14, bold: last, color: colours[j], align: j ? "center" : "left", valign: "middle" }));
  });
})();

// ---- 07 E3 chart ------------------------------------------------------------------
(() => {
  const s = slide("The coloured part is the cache's fault, the grey part the filter misses on its own. The safe setting removes all of the first and none of the second.");
  label(s, "// 06 — Whose Fault Is Each Leak");
  title(s, "The cache's fault, separated from the filter's");
  const f = img("fig_defence_settings.png");
  const w = 12.1, h = w * f.ratio;
  s.addImage({ path: f.path, x: 0.6, y: 1.9, w, h: Math.min(h, 4.5) });
  s.addText(`What is still served with every hit re-checked, about ${p0(A.all.served.clean.filter_miss)}, is exactly what the filter misses when asked directly.`,
    { x: MX, y: 6.45, w: W - 2 * MX, h: 0.35, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 13, italic: true, color: MUTED, align: "center" });
})();

// ---- 08 E4 filter alone --------------------------------------------------------------
(() => {
  const s = slide("New in Phase 4. The filter is nearly perfect on ordinary text, but weak on look-alikes and on conversational attacks. A cache defence cannot fix the filter.");
  label(s, "// 07 — The Filter on its Own");
  title(s, "Two numbers that must not be pooled");
  const rows = [
    ["Ordinary honest text", `${FA_ORD.n.toLocaleString()} texts`, `${FA_ORD.k} blocked (${p1(FA_ORD.rate)})`, GREEN],
    ["Look-alike honest text", `${FA_LOOK.n.toLocaleString()} texts`, `${p1(FA_LOOK.rate)} blocked`, RED],
    ["Attacks: jayavibhav", `${DET_JAY.n.toLocaleString()} attacks`, `${p1(DET_JAY.rate)} caught`, GREEN],
    ["Attacks: deepset (conversational)", `${DET_DS.n.toLocaleString()} attacks`, `${p1(DET_DS.rate)} caught`, RED],
  ];
  rows.forEach(([k, n, v, col], i) => {
    const y = 1.95 + i * 0.95;
    card(s, 0.6, y, 7.4, 0.8, i % 2 ? ALT : WHITE);
    s.addText(k, { x: 0.85, y, w: 3.6, h: 0.8, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 14, color: NAVY, valign: "middle" });
    s.addText(n, { x: 4.3, y, w: 1.5, h: 0.8, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 12, color: MUTED, valign: "middle" });
    s.addText(v, { x: 5.7, y, w: 2.2, h: 0.8, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 15, bold: true, color: col, valign: "middle", align: "right" });
  });
  const cx = 8.35, cw = 4.35;
  card(s, cx, 1.95, cw, 3.65);
  s.addText("WHAT THIS MEANS", { x: cx + 0.4, y: 2.25, w: 3.5, h: 0.26, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 11, color: GOLD });
  s.addText([
    { text: "Ordinary users are almost never blocked. ", options: { color: TEXT, breakLine: true } },
    { text: " ", options: { breakLine: true } },
    { text: "But the filter is easily confused by attack-like words, and misses most conversational attacks. ", options: { color: TEXT, breakLine: true } },
    { text: " ", options: { breakLine: true } },
    { text: "Re-checking hits removes the risk the cache adds; it cannot repair the filter.", options: { color: GOLD, bold: true } },
  ], { x: cx + 0.4, y: 2.6, w: cw - 0.75, h: 2.9, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 13, lineSpacingMultiple: 1.2, valign: "top" });
  s.addText(`Area under the curve: ${SCR.auc_ordinary.toFixed(3)} on ordinary text, ${SCR.auc_lookalike.toFixed(3)} on look-alikes. Moving the block threshold barely changes either.`,
    { x: MX, y: 5.95, w: W - 2 * MX, h: 0.5, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 12.5, italic: true, color: MUTED });
})();

// ---- 09 router + mitigations -----------------------------------------------------------
(() => {
  const s = slide("The other three layers, briefly. Routing saves real money on easy questions; the guard and the limiter were shown live.");
  label(s, "// 08 — Cost and the Other Layers");
  title(s, `Easy questions cost ${EASY_SAVED}% less`);
  const c = RTR.cost_by_label;
  const rows = [["Easy (20)", c.easy.strong, c.easy.router, GREEN], ["Hard (20)", c.hard.strong, c.hard.router, TEXT],
                [`All ${RTR.questions}`, RTR.strong_cost_usd, RTR.router_cost_usd, TEXT]];
  ["", "ALWAYS GPT-4O", "MODEL PICKER", "SAVED"].forEach((h, j) => s.addText(h, { x: [0.9, 3.3, 5.0, 6.7][j], y: 1.95, w: 1.7, h: 0.3,
    isTextBox: true, margin: 0, fontFace: FONT, fontSize: 10, color: GOLD, align: j ? "center" : "left" }));
  rows.forEach(([k, strong, router, col], i) => {
    const y = 2.35 + i * 0.85;
    card(s, 0.6, y, 7.4, 0.72, i % 2 ? ALT : WHITE);
    [[k, 0.9, 2.4, NAVY, 14, "left"], [`$${strong.toFixed(5)}`, 3.3, 1.7, MUTED, 14, "center"],
     [`$${router.toFixed(5)}`, 5.0, 1.7, MUTED, 14, "center"], [`${Math.round(100 * (1 - router / strong))}%`, 6.7, 1.1, col, 20, "center"]]
      .forEach(([v, x, w, colr, fs, al]) => s.addText(v, { x, y, w, h: 0.72, isTextBox: true, margin: 0, fontFace: FONT, fontSize: fs, color: colr, align: al, valign: "middle" }));
  });
  const cx = 8.35, cw = 4.35;
  card(s, cx, 1.95, cw, 4.55);
  s.addText("SHOWN LIVE", { x: cx + 0.4, y: 2.25, w: 3.5, h: 0.26, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 11, color: GOLD });
  s.addText([
    { text: "Output guard: ", options: { color: TEXT, bold: true } },
    { text: "a cached answer carrying a cookie-stealing script was refused with 403 in block mode.", options: { color: TEXT, breakLine: true } },
    { text: " ", options: { breakLine: true } },
    { text: "Rate limit: ", options: { color: TEXT, bold: true } },
    { text: `${REFUSED} of one caller's burst refused with 429; other callers unaffected.`, options: { color: TEXT, breakLine: true } },
    { text: " ", options: { breakLine: true } },
    { text: "Failover: ", options: { color: TEXT, bold: true } },
    { text: "a failed model call was answered by the fallback model.", options: { color: TEXT } },
  ], { x: cx + 0.4, y: 2.6, w: cw - 0.75, h: 3.8, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 13, lineSpacingMultiple: 1.2, valign: "top" });
})();

// ---- 10 the paper -------------------------------------------------------------------
(() => {
  const s = slide("The paper is the main deliverable of this phase. Show the title and what makes it credible: every number regenerated from the logs, every reference checked.");
  label(s, "// 09 — The Paper");
  title(s, "Written up as a journal paper");
  card(s, 0.6, 1.85, 12.1, 1.25);
  s.addText("Measuring and Closing a Semantic-Cache Bypass of Prompt-Injection Filters in Large Language Model Gateways",
    { x: 0.95, y: 1.85, w: 11.4, h: 1.25, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 19, color: NAVY, italic: true, valign: "middle" });
  const facts = [
    ["13", "pages, two columns, journal layout"],
    [String(REFS), "references, each checked against its published record"],
    ["5", "experiments, every rate with a 95% range"],
    ["1", "command rebuilds every number and figure from the logs"],
  ];
  facts.forEach(([n, t], i) => {
    const x = 0.6 + i * 3.05;
    card(s, x, 3.4, 2.9, 2.0);
    s.addText(n, { x: x + 0.3, y: 3.6, w: 2.4, h: 0.8, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 38, color: GOLD });
    s.addText(t, { x: x + 0.3, y: 4.45, w: 2.4, h: 0.85, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 12, color: MUTED, lineSpacingMultiple: 1.1, valign: "top" });
  });
  s.addText("Prepared for submission to the Arabian Journal for Science and Engineering, with a cover letter.",
    { x: MX, y: 5.75, w: W - 2 * MX, h: 0.4, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 14, italic: true, color: TEXT });
})();

// ---- 11 timeline ------------------------------------------------------------------
(() => {
  const s = slide("All four phases are done. Each ended with one measured, demonstrable result.");
  label(s, "// 10 — Timeline");
  title(s, "Project roadmap: August – November 2026");
  const phases = [
    ["18–22 AUG", "Phase 1 — Establish the Problem", "Offline proof-of-concept, threshold sweep, architecture definition, synopsis."],
    ["23 AUG–26 SEP", "Phase 2 — Build the Gateway", "Reproduced the bypass on our own running system; first real bypass-rate figure."],
    ["27 SEP–24 OCT", "Phase 3 — Build the Defence", "Verdict-tagged cache, re-checking, model picker, output guard, rate limits."],
    ["25 OCT–14 NOV", "Phase 4 — Evaluate & Publish", "Confidence ranges, the filter on its own, journal paper and submission package."],
  ];
  s.addShape(pres.ShapeType.line, { x: 1.55, y: 2.2, w: 0, h: 4.5, line: { color: LINE, width: 1.5 } });
  phases.forEach(([when, h, b], i) => {
    const y = 1.95 + i * 1.18;
    s.addText(when, { x: 0.25, y: y + 0.08, w: 1.1, h: 0.45, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 10.5, color: MUTED, align: "right", valign: "top" });
    s.addShape(pres.ShapeType.ellipse, { x: 1.44, y: y + 0.12, w: 0.22, h: 0.22, fill: { color: GREEN }, line: { color: WHITE, width: 1.5 } });
    card(s, 1.95, y, 10.75, 0.95);
    s.addText(h, { x: 2.3, y: y + 0.12, w: 7, h: 0.35, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 16, color: NAVY });
    s.addText(b, { x: 2.3, y: y + 0.52, w: 7.3, h: 0.3, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 11.5, color: MUTED });
    pill(s, 9.7, y + 0.2, 2.85, 0.42, "COMPLETE", GREEN, WHITE);
  });
})();

// ---- 12 limits & future work -------------------------------------------------------
(() => {
  const s = slide("Be plain about the limits, then point forward. None of the limits change the main result.");
  label(s, "// 11 — Limits & Future Work");
  title(s, "What bounds the result, and what comes next");
  const risks = [
    ["LIMIT", SLATE, "Mocked model replies", "The attack runs mock the reply, because a cached answer never reaches the model. Filter, embedder and stores are real."],
    ["LIMIT", SLATE, "One filter, one embedder", "Absolute rates will differ for other components; the structure of the result does not."],
    ["FUTURE", BLUE, "Other filters and routes", "LLM-based guards, other embedders, pre-filled and cross-tenant caches."],
    ["FUTURE", GOLD, "Adaptive attackers", "Rewordings that match the poison and also evade the filter; add a check that the answer fits the question."],
  ];
  risks.forEach(([st, col, h, b], i) => {
    const y = 1.85 + i * 1.25;
    card(s, 0.6, y, 12.1, 1.1);
    pill(s, 0.85, y + 0.18, 1.85, 0.42, st, col);
    s.addText(h, { x: 3.0, y, w: 3.3, h: 1.1, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 15, color: NAVY, valign: "middle" });
    s.addText(b, { x: 6.4, y, w: 6.05, h: 1.1, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 12, color: MUTED, lineSpacingMultiple: 1.15, valign: "middle" });
  });
})();

// ---- 13 thank you -------------------------------------------------------------------
(() => {
  const s = slide("Close on the result and take questions.", "NAVY");
  s.addText("Thank You", { x: MX, y: 2.6, w: 8, h: 0.95, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 52, color: WHITE });
  s.addText("Questions and discussion", { x: MX, y: 3.55, w: 8, h: 0.45, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 19, italic: true, color: "D5DAE3" });
  s.addShape(pres.ShapeType.line, { x: MX - 0.08, y: 4.15, w: 3.0, h: 0, line: { color: GOLD, width: 1 } });
  s.addText("SentryGate — Security-Aware Semantic Caching Gateway for LLM Applications", { x: MX, y: 4.42, w: 10, h: 0.32, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 14, color: "A5ADBB" });
  s.addText("Divyansh Sharma · Sarvagya Dabas · Yashvit Gauri", { x: MX, y: 4.82, w: 10, h: 0.32, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 14, color: "A5ADBB" });
  s.addText("FINAL REVIEW — 14 NOVEMBER 2026", { x: MX, y: 6.85, w: 6, h: 0.3, isTextBox: true, margin: 0, fontFace: FONT, fontSize: 12, color: GOLD });
})();

if (D.pageNo !== TOTAL) throw new Error(`expected ${TOTAL} slides, built ${D.pageNo}`);
const out = path.join(ROOT, "reports/out/SentryGate_Progress_Report_4.pptx");
fs.mkdirSync(path.dirname(out), { recursive: true });
pres.writeFile({ fileName: out }).then(() => console.log(`wrote reports/out/SentryGate_Progress_Report_4.pptx (${D.pageNo} slides)`));
