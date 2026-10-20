"""Draw every data figure in the journal paper, in one style.

Reads only the committed reports, never a typed-in number:

    data/week4/report.json     the bypass sweep (Phase 2)
    data/phase3/report.json    the defence settings (Phase 3)
    data/phase4/report.json    ranges, the ablation, the filter alone, the load test
    data/router/report.json    the model picker (Phase 3, real paid calls)

Writes SVG files to paper/journal/figures/. SVG stays sharp at any zoom and
in print; text is drawn as paths, so the PDF looks the same on any machine.

Run inside the attacks image (it has the pinned matplotlib):
    make journal-figures
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "figures"

INK = "#1a1a1a"
MUTED = "#5f6368"
GRID = "#e3e3e3"
NAVY = "#1f3b73"
TEAL = "#2a8c82"
AMBER = "#d98e04"
RED = "#b23a2e"
GREY = "#a7abb0"
LIGHT = "#d9dce0"

plt.rcParams.update({
    "font.family": "STIXGeneral",          # ships with matplotlib, Times-like
    "mathtext.fontset": "stix",
    "font.size": 9,
    "axes.titlesize": 9.5,
    "axes.labelsize": 9,
    "axes.edgecolor": "#888888",
    "axes.linewidth": 0.6,
    "xtick.color": INK,
    "ytick.color": INK,
    "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5,
    "legend.fontsize": 8,
    "legend.frameon": False,
    "svg.fonttype": "path",
    "figure.dpi": 150,
})


def read(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def style(ax, grid_axis: str = "y") -> None:
    ax.grid(True, axis=grid_axis, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def save(fig, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{name}.svg", bbox_inches="tight", pad_inches=0.03)
    plt.close(fig)
    print(f"  wrote {OUT / name}.svg")


# --- Fig: bypass rate against the cache threshold ----------------------------------

def bypass_vs_threshold(p4: dict) -> None:
    sweep = p4["earlier"]["bypass_by_threshold"]
    ts = sorted(sweep, key=float)
    x = [float(t) for t in ts]
    fig, ax = plt.subplots(figsize=(3.4, 2.5))
    for fam, colour, label, marker in (("lazy", RED, "Lazy edits", "o"), ("all", NAVY, "All rewordings", "s"),
                                       ("rewrite", TEAL, "Full paraphrases", "^")):
        y = [sweep[t][fam]["rate"] for t in ts]
        lo = [sweep[t][fam]["ci"][0] for t in ts]
        hi = [sweep[t][fam]["ci"][1] for t in ts]
        ax.fill_between(x, lo, hi, color=colour, alpha=0.15, linewidth=0)
        ax.plot(x, y, color=colour, marker=marker, markersize=3.5, linewidth=1.3, label=label)
    ax.axvspan(0.85, 0.95, color=LIGHT, alpha=0.5, linewidth=0)
    ax.text(0.90, 44, "settings a real\nproduct would use", ha="center", fontsize=7.5, color=MUTED)
    ax.set_xlabel("Cache similarity threshold")
    ax.set_ylabel("Bypass rate (%)")
    ax.set_ylim(0, 103)
    ax.set_xlim(0.64, 0.96)
    ax.invert_xaxis()
    ax.legend(loc="lower right")
    style(ax)
    save(fig, "fig_bypass_threshold")


# --- Fig: the Phase 3 defence settings ---------------------------------------------

P3_ARMS = [("base", "No defence"), ("filter", "Label match"), ("recheck", "Re-check\nrisky hits"),
           ("both", "Label match +\nre-check risky"), ("all", "Label match +\nre-check all")]


def defence_settings(p3: dict, p4: dict) -> None:
    ranges = p4["earlier"]["phase3_cache_caused"]
    fig, ax = plt.subplots(figsize=(7.0, 2.6))
    xs = range(len(P3_ARMS))
    width = 0.36
    for offset, label, colour, name in ((-width / 2, "clean", RED, "Poison saved as clean (realistic)"),
                                        (width / 2, "attack", NAVY, "Poison saved as attack (easy)")):
        cause = [p3["arms"][t]["served"][label]["cache_caused"] for t, _ in P3_ARMS]
        miss = [p3["arms"][t]["served"][label]["filter_miss"] for t, _ in P3_ARMS]
        lo = [cause[i] - ranges[f"{t}/{label}"]["ci"][0] for i, (t, _) in enumerate(P3_ARMS)]
        hi = [ranges[f"{t}/{label}"]["ci"][1] - cause[i] for i, (t, _) in enumerate(P3_ARMS)]
        pos = [x + offset for x in xs]
        ax.bar(pos, cause, width, color=colour, label=f"Cache-caused, {name.lower()}")
        ax.bar(pos, miss, width, bottom=cause, color=LIGHT, edgecolor=GREY, linewidth=0.4,
               label="Missed by the filter itself" if label == "clean" else None)
        ax.errorbar(pos, cause, yerr=[lo, hi], fmt="none", ecolor=INK, elinewidth=0.7, capsize=2)
        for p_, c_, h_ in zip(pos, cause, hi):
            # Above the top of the range, clear of the error bar.
            ax.text(p_, c_ + h_ + 1.2, f"{c_:.1f}", ha="center", fontsize=7.5, color=colour, weight="bold")
    ax.set_xticks(list(xs))
    ax.set_xticklabels([n for _, n in P3_ARMS])
    ax.set_ylabel("Rewordings served the poison (%)")
    ax.set_ylim(0, 85)
    ax.legend(loc="upper right", ncol=1)
    style(ax)
    save(fig, "fig_defence_settings")


# --- Fig: the ablation -------------------------------------------------------------

ABL = [("full", "Full\nsystem"), ("no_recheck", "No\nre-check"), ("no_label", "No label\nmatch"),
       ("no_guard", "No output\nguard"), ("no_screening", "No safety\nfilter"), ("none", "No\ndefence"),
       ("safe_order", "Filter\nfirst")]


def ablation(p4: dict) -> None:
    arms = p4["ablation"]["arms"]
    tags = [(t, n) for t, n in ABL if t in arms]
    fig, (left, right) = plt.subplots(1, 2, figsize=(7.0, 2.7), gridspec_kw={"width_ratios": [1.55, 1]})
    xs = list(range(len(tags)))
    width = 0.27
    series = (("secret/clean", "served", RED, "Text poison, saved as clean"),
              ("secret/attack", "served", NAVY, "Text poison, saved as attack"),
              ("script/clean", "served", AMBER, "Script poison, saved as clean"))
    for i, (cell, key, colour, name) in enumerate(series):
        vals = [arms[t]["cells"][cell][key]["rate"] for t, _ in tags]
        lo = [v - arms[t]["cells"][cell][key]["ci"][0] for v, (t, _) in zip(vals, tags)]
        hi = [arms[t]["cells"][cell][key]["ci"][1] - v for v, (t, _) in zip(vals, tags)]
        pos = [x + (i - 1) * width for x in xs]
        left.bar(pos, vals, width, color=colour, label=name)
        left.errorbar(pos, vals, yerr=[lo, hi], fmt="none", ecolor=INK, elinewidth=0.6, capsize=1.5)
    left.set_xticks(xs)
    left.set_xticklabels([n for _, n in tags], fontsize=7.5)
    left.set_ylabel("Attack rewordings served the poison (%)")
    left.set_ylim(0, 100)
    left.legend(loc="upper left", fontsize=7.2)
    left.set_title("(a) Safety: poison served (lower is better)")
    style(left)

    hit = [arms[t]["hit_p50_ms"] or 0 for t, _ in tags]
    right.barh([n.replace("\n", " ") for _, n in tags], hit, color=TEAL)
    for i, (v, (t, _)) in enumerate(zip(hit, tags)):
        right.text(v + 2, i, f"{v:.0f} ms · {arms[t]['honest_hit_rate']:.0f}% hits", va="center", fontsize=7.3)
    right.invert_yaxis()
    right.set_xlim(0, max(hit) * 1.75)
    right.set_xlabel("Honest cache hit, median latency (ms)")
    right.set_title("(b) Cost to honest users")
    right.tick_params(axis="y", labelsize=7.5)
    style(right, "x")
    fig.tight_layout(w_pad=1.2)
    save(fig, "fig_ablation")


# --- Fig: the filter alone ----------------------------------------------------------

def filter_alone(p4: dict) -> None:
    s = p4["screening"]
    fig, (left, right) = plt.subplots(1, 2, figsize=(7.0, 2.55))
    bins = [i / 20 for i in range(21)]
    for key, colour, label in (("ordinary", TEAL, "Ordinary honest text"),
                               ("lookalike", AMBER, "Look-alike honest text"),
                               ("attack", RED, "Attacks")):
        scores = s["scores"][key]
        # Share of each set, so sets of different sizes compare.
        left.hist(scores, bins=bins, weights=[100 / len(scores)] * len(scores), color=colour, linewidth=1.5,
                  histtype="step", label=f"{label} (n = {len(scores):,})")
    left.axvline(0.5, color=INK, linestyle="--", linewidth=0.8)
    left.set_yscale("log")
    left.set_ylim(0.05, 150)
    left.set_xlabel("Filter's injection score (block at 0.5, dashed)")
    left.set_ylabel("Share of the set (%, log scale)")
    left.set_title("(a) Score distribution")
    left.legend(loc="upper center", fontsize=7.2, frameon=True, facecolor="white", edgecolor="none", framealpha=1)
    style(left)

    curve = s["curve"]
    for key, colour, marker, name, auc in (
            ("false_alarm_ordinary", TEAL, "o", "Ordinary honest text", s["auc_ordinary"]),
            ("false_alarm_lookalike", AMBER, "s", "Look-alike honest text", s["auc_lookalike"])):
        right.plot([c[key] for c in curve], [c["detection"] for c in curve], color=colour, marker=marker,
                   markersize=3, linewidth=1.2, label=f"{name} (AUC {auc:.3f})")
        for c in curve:
            if c["threshold"] == 0.5:
                right.annotate("0.5", (c[key], c["detection"]), textcoords="offset points", xytext=(5, -10),
                               fontsize=7.3, color=MUTED)
    right.plot([0, 100], [0, 100], color=GREY, linestyle=":", linewidth=0.8)
    right.set_xlim(0, 100)
    right.set_ylim(0, 100)
    right.set_xlabel("Honest texts blocked (%)")
    right.set_ylabel("Attacks caught (%)")
    right.set_title("(b) Catches against false alarms, by block threshold")
    right.legend(loc="lower right", fontsize=7.2)
    style(right, "both")
    fig.tight_layout(w_pad=1.5)
    save(fig, "fig_filter_alone")


# --- Fig: the load test --------------------------------------------------------------

def load_test(p4: dict) -> None:
    runs = p4["load"]
    fig, (left, right) = plt.subplots(1, 2, figsize=(7.0, 2.5))
    for tag, colour, marker in (("open", GREY, "o"), ("defended", NAVY, "s")):
        if tag not in runs:
            continue
        steps = runs[tag]["steps"]
        users = [st["users"] for st in steps]
        name = runs[tag]["name"]
        left.plot(users, [st["throughput_rps"] for st in steps], color=colour, marker=marker, markersize=3.5,
                  linewidth=1.3, label=name)
        for kind, ls in (("hit", "-"), ("rechecked_hit", "-")):
            vals = [(st["outcomes"].get(kind) or {}).get("p50") for st in steps]
            if any(v is not None for v in vals):
                right.plot(users, vals, color=colour, marker=marker, markersize=3.5, linewidth=1.3, linestyle=ls,
                           label=f"{name}: {'re-checked hit' if kind == 'rechecked_hit' else 'hit'} p50")
            vals99 = [(st["outcomes"].get(kind) or {}).get("p99") for st in steps]
            if any(v is not None for v in vals99):
                right.plot(users, vals99, color=colour, marker=marker, markersize=3, linewidth=0.9,
                           linestyle="--", label=f"{name}: p99")
    left.set_xlabel("Concurrent users")
    left.set_ylabel("Requests per second")
    left.set_title("(a) Throughput")
    left.legend(loc="upper left")
    right.set_xlabel("Concurrent users")
    right.set_ylabel("Latency of a cache hit (ms)")
    right.set_yscale("log")
    right.set_title("(b) Cache-hit latency under load")
    right.legend(loc="upper left", fontsize=6.8)
    for ax in (left, right):
        ax.set_xscale("log")
        ax.set_xticks([1, 5, 10, 25, 50])
        ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        style(ax, "both")
    fig.tight_layout(w_pad=1.5)
    save(fig, "fig_load")


# --- Fig: the model picker ------------------------------------------------------------

def router(r: dict) -> None:
    fig, ax = plt.subplots(figsize=(3.4, 2.3))
    groups = [("Easy (20)", "easy"), ("Hard (20)", "hard")]
    xs = range(len(groups))
    width = 0.36
    strong = [r["cost_by_label"][k]["strong"] * 100 for _, k in groups]
    picked = [r["cost_by_label"][k]["router"] * 100 for _, k in groups]
    ax.bar([x - width / 2 for x in xs], strong, width, color=GREY, label="Always the strong model")
    ax.bar([x + width / 2 for x in xs], picked, width, color=TEAL, label="Model picker")
    for x, s_, p_ in zip(xs, strong, picked):
        ax.text(x + width / 2, p_ + 0.15, f"−{100 * (1 - p_ / s_):.0f}%", ha="center", fontsize=8, color=TEAL,
                weight="bold")
    ax.set_xticks(list(xs))
    ax.set_xticklabels([g for g, _ in groups])
    ax.set_ylabel("Cost of 20 questions (US cents)")
    ax.set_ylim(0, max(strong) * 1.35)
    ax.legend(loc="upper left", ncol=1)
    style(ax)
    save(fig, "fig_router")


def main() -> int:
    p4 = read("data/phase4/report.json")
    bypass_vs_threshold(p4)
    defence_settings(read("data/phase3/report.json"), p4)
    if p4.get("ablation"):
        ablation(p4)
    if p4.get("screening"):
        filter_alone(p4)
    if p4.get("load"):
        load_test(p4)
    router(read("data/router/report.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
