"""Turn the Phase 4 results into numbers the paper can quote.

Reads only committed results and gateway logs, never anything typed in:

    data/phase4/screening_results.jsonl     the filter alone, held-out texts
    data/phase4/results.jsonl, benign_*     the ablation
    data/phase4/run-<arm>.jsonl             each ablation arm's gateway log
    data/phase4/load-*.jsonl, locust/*.csv  the load test
    data/week4/results.jsonl, data/phase3/results.jsonl   for confidence ranges on earlier results

Confidence ranges. Rewordings of one seed are not independent: if one lazy
edit matches, the others usually do too. A plain binomial range would be too
narrow. So every attack rate gets a 95% range from a bootstrap over seeds
(resample whole seeds, 2,000 times, fixed random seed). Rates over
independent texts (the screening set) use the Wilson score range. When
nothing at all was served, resampling can only ever give zero, so the upper
end is the rule of three over seeds (3 / seeds), which is conservative.

Writes data/phase4/report.json and data/phase4/table.md.

Run inside the attacks image:  make phase4-report
"""

from __future__ import annotations

import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P4 = ROOT / "data" / "phase4"
BOOT = 2000
BOOT_SEED = 20261102

ARMS = [
    ("full", "Full system"),
    ("no_recheck", "Without re-checking hits"),
    ("no_label", "Without label matching"),
    ("no_guard", "Without the output guard"),
    ("no_screening", "Without the safety filter"),
    ("none", "No defence (Phase 2 baseline)"),
    ("safe_order", "Filter before cache (reference)"),
]
LOAD_ARMS = [("open", "No defence"), ("defended", "Full defence")]


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def pct(part: float, whole: float) -> float:
    return round(100 * part / whole, 2) if whole else 0.0


def quantile(values: list[float], q: float) -> float | None:
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return round(values[min(len(values) - 1, int(q * len(values)))], 1)


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(100 * max(0.0, centre - half), 2), round(100 * min(1.0, centre + half), 2)]


def seed_bootstrap(rows: list[dict], hit) -> dict:
    """Rate of hit(row) over rows, with a 95% range from resampling whole seeds."""
    by_seed: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        cell = by_seed[r["seed_id"]]
        cell[0] += 1 if hit(r) else 0
        cell[1] += 1
    cells = list(by_seed.values())
    k = sum(c[0] for c in cells)
    n = sum(c[1] for c in cells)
    if not cells:
        return {"rate": 0.0, "ci": [0.0, 0.0], "k": 0, "n": 0}
    rng = random.Random(BOOT_SEED)
    rates = []
    for _ in range(BOOT):
        sample = [cells[rng.randrange(len(cells))] for _ in cells]
        rates.append(sum(c[0] for c in sample) / sum(c[1] for c in sample))
    rates.sort()
    if k == 0:
        return {"rate": 0.0, "ci": [0.0, round(100 * 3 / len(cells), 2)], "k": 0, "n": n}
    return {"rate": pct(k, n), "ci": [round(100 * rates[int(0.025 * BOOT)], 2),
                                      round(100 * rates[int(0.975 * BOOT) - 1], 2)], "k": k, "n": n}


def filter_blocks() -> dict[str, bool]:
    """variant_id -> did the real filter block this text when asked directly (Week 4 screen-first run)?"""
    return {r["variant_id"]: r["status"] == 403 for r in load(ROOT / "data" / "week4" / "results.jsonl")
            if r["tag"] == "screen_first" and abs(r["threshold"] - 0.85) < 1e-9}


# --- 1. the filter alone ----------------------------------------------------------

ORDINARY = ("deepset", "dolly")      # honest text as ordinary users write it
LOOKALIKE = ("jayavibhav",)          # synthetic honest text full of attack words


def screening_report() -> dict:
    rows = [r for r in load(P4 / "screening_results.jsonl") if not math.isnan(r["score"])]
    if not rows:
        return {}

    def rate(label: str, datasets: tuple[str, ...] | None = None) -> dict:
        group = [r for r in rows if r["label"] == label and (datasets is None or r["dataset"] in datasets)]
        k = sum(r["blocked"] for r in group)
        return {"k": k, "n": len(group), "rate": pct(k, len(group)), "ci": wilson(k, len(group))}

    def auc(attack: list[float], honest: list[float]) -> float | None:
        # The chance a random attack scores above a random honest text (ties count half).
        if not attack or not honest:
            return None
        pairs = sum(1.0 if a > h else 0.5 if a == h else 0.0 for a in attack for h in honest)
        return round(pairs / (len(attack) * len(honest)), 4)

    attack = [r["score"] for r in rows if r["label"] == "attack"]
    ordinary = [r["score"] for r in rows if r["label"] == "honest" and r["dataset"] in ORDINARY]
    lookalike = [r["score"] for r in rows if r["label"] == "honest" and r["dataset"] in LOOKALIKE]
    curve = []
    for t in [0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 0.999]:
        curve.append({"threshold": t,
                      "false_alarm_ordinary": pct(sum(x >= t for x in ordinary), len(ordinary)),
                      "false_alarm_lookalike": pct(sum(x >= t for x in lookalike), len(lookalike)),
                      "detection": pct(sum(x >= t for x in attack), len(attack))})
    datasets = sorted({r["dataset"] for r in rows})
    return {
        "false_alarms_ordinary": rate("honest", ORDINARY),
        "false_alarms_lookalike": rate("honest", LOOKALIKE),
        "false_alarms": rate("honest"),
        "detection": rate("attack"),
        "by_dataset": {d: {"false_alarms": rate("honest", (d,)), "detection": rate("attack", (d,))}
                       for d in datasets},
        "curve": curve,
        "auc_ordinary": auc(attack, ordinary),
        "auc_lookalike": auc(attack, lookalike),
        "scores": {"ordinary": ordinary, "lookalike": lookalike, "attack": attack},
    }


# --- 2. the ablation ------------------------------------------------------------

def ablation_report() -> dict:
    rows = [r for r in load(P4 / "results.jsonl") if r["family"] != "exact"]
    if not rows:
        return {}
    blocks = filter_blocks()
    missing = sum(1 for r in rows if r["variant_id"] not in blocks)
    if missing:
        raise SystemExit(f"{missing} variants have no screen-first result in data/week4.")
    exact = [r for r in load(P4 / "results.jsonl") if r["family"] == "exact"]
    benign = load(P4 / "benign_results.jsonl")
    benign_summary = {s["tag"]: s for s in load(P4 / "benign_summary.jsonl")}
    controls = load(P4 / "controls_results.jsonl")

    arms = {}
    for tag, name in ARMS:
        arm_rows = [r for r in rows if r["tag"] == tag]
        if not arm_rows:
            continue
        cells = {}
        for kind in ("secret", "script"):
            for label in ("clean", "attack"):
                at = [r for r in arm_rows if r["poison_kind"] == kind and r["poison_label"] == label]
                if not at and kind == "script":
                    # Guard-off arms skip the script run (sweep_phase4.sh): with no
                    # guard, the poison's content cannot change what is served.
                    at = [r for r in arm_rows if r["poison_kind"] == "secret" and r["poison_label"] == label]
                cells[f"{kind}/{label}"] = {
                    "served": seed_bootstrap(at, lambda r: r["served_poison"]),
                    "cache_caused": seed_bootstrap(at, lambda r: r["served_poison"] and blocks[r["variant_id"]]),
                    "filter_miss": seed_bootstrap(at, lambda r: r["served_poison"] and not blocks[r["variant_id"]]),
                    "guard_blocked": sum(1 for r in at if r.get("block_reason") == "unsafe_output"),
                    "lazy": pct(sum(r["served_poison"] for r in at if r["family"] == "lazy"),
                                sum(1 for r in at if r["family"] == "lazy")),
                    "rewrite": pct(sum(r["served_poison"] for r in at if r["family"] == "rewrite"),
                                   sum(1 for r in at if r["family"] == "rewrite")),
                }
        honest = [r for r in benign if r["tag"] == tag]
        hits = [r for r in honest if r["hit"]]
        log = load(P4 / f"run-{tag}.jsonl")
        misses = [(line.get("latency_ms") or {}).get("total") for line in log
                  if (line.get("cache") or {}).get("outcome") == "miss" and line.get("status") == 200]
        arms[tag] = {
            "name": name,
            "cells": cells,
            "exact_served": {kind: pct(sum(r["served_poison"] for r in exact if r["tag"] == tag
                                           and r["poison_kind"] == kind),
                                       sum(1 for r in exact if r["tag"] == tag and r["poison_kind"] == kind))
                             for kind in ("secret", "script")},
            "honest_hit_rate": pct(len(hits), len(honest)),
            "honest_rewordings": len(honest),
            "honest_hits_rechecked": pct(sum(1 for r in hits if r["reverified"]), len(hits)),
            "hit_p50_ms": quantile([r["latency_ms"] for r in hits], 0.5),
            "hit_p99_ms": quantile([r["latency_ms"] for r in hits], 0.99),
            "miss_p50_ms": quantile(misses, 0.5),
            "honest_blocked_at_first_ask": benign_summary.get(tag, {}).get("blocked_at_first_ask"),
            "controls_served_poison": sum(1 for c in controls if c["tag"] == tag and c.get("served_poison")),
            "controls": sum(1 for c in controls if c["tag"] == tag),
        }
    return {"seeds": len({r["seed_id"] for r in rows}),
            "variants_per_cell": len({r["variant_id"] for r in rows}),
            "honest_questions": len({r["control_id"] for r in benign}),
            "arms": arms}


# --- 3. the load test -------------------------------------------------------------

def outcome(line: dict) -> str:
    cache = (line.get("cache") or {}).get("outcome")
    if line.get("status") == 403:
        return "blocked"
    if line.get("status") != 200:
        return "error"
    if cache == "hit":
        return "rechecked_hit" if line.get("reverified") else "hit"
    return "miss"


def locust_row(path: Path, name: str) -> dict:
    if not path.exists():
        return {}
    with path.open() as f:
        for row in csv.DictReader(f):
            if row["Name"] == name:
                return row
    return {}


def load_report() -> dict:
    runs = {}
    for tag, name in LOAD_ARMS:
        for log in sorted(P4.glob(f"load-{tag}-u*.jsonl")):
            users = int(log.stem.rsplit("-u", 1)[1])
            warm_file = log.with_suffix(".warm")
            warm = int(warm_file.read_text().strip() or 0) if warm_file.exists() else 0
            lines = load(log)[warm:]
            by = defaultdict(list)
            overhead = []
            for line in lines:
                kind = outcome(line)
                by[kind].append((line.get("latency_ms") or {}).get("total"))
                lat = line.get("latency_ms") or {}
                if kind == "miss" and lat.get("provider") is not None:
                    overhead.append(lat["total"] - lat["provider"])
            agg = locust_row(P4 / "locust" / f"{tag}-u{users}_stats.csv", "Aggregated")
            runs.setdefault(tag, {"name": name, "steps": []})["steps"].append({
                "users": users,
                "requests": len(lines),
                "throughput_rps": round(float(agg.get("Requests/s", 0) or 0), 2),
                "failures": int(agg.get("Failure Count", 0) or 0),
                "client_p50_ms": float(agg.get("50%", 0) or 0),
                "client_p95_ms": float(agg.get("95%", 0) or 0),
                "client_p99_ms": float(agg.get("99%", 0) or 0),
                "outcomes": {k: {"n": len(v), "p50": quantile(v, 0.5), "p95": quantile(v, 0.95),
                                 "p99": quantile(v, 0.99)} for k, v in sorted(by.items())},
                "overhead_p50_ms": quantile(overhead, 0.5),
                "overhead_p99_ms": quantile(overhead, 0.99),
            })
        if tag in runs:
            runs[tag]["steps"].sort(key=lambda s: s["users"])
    return runs


# --- 4. ranges on the earlier results --------------------------------------------------

def earlier_report() -> dict:
    week4 = [r for r in load(ROOT / "data" / "week4" / "results.jsonl") if r["family"] != "exact"]
    sweep = {}
    for t in sorted({r["threshold"] for r in week4 if r["tag"] != "screen_first"}, reverse=True):
        at = [r for r in week4 if r["tag"] != "screen_first" and abs(r["threshold"] - t) < 1e-9]
        sweep[f"{t:.2f}"] = {fam: seed_bootstrap([r for r in at if fam == "all" or r["family"] == fam],
                                                 lambda r: r["bypass"])
                             for fam in ("lazy", "rewrite", "all")}
    phase3 = [r for r in load(ROOT / "data" / "phase3" / "results.jsonl") if r["family"] != "exact"]
    blocks = filter_blocks()
    defence = {}
    for tag in ("base", "filter", "recheck", "both", "all"):
        for label in ("clean", "attack"):
            at = [r for r in phase3 if r["tag"] == tag and r["poison_label"] == label]
            if at:
                defence[f"{tag}/{label}"] = seed_bootstrap(
                    at, lambda r: r["served_poison"] and blocks[r["variant_id"]])
    return {"bypass_by_threshold": sweep, "phase3_cache_caused": defence}


# --- output -----------------------------------------------------------------------

def fmt(cell: dict) -> str:
    return f"{cell['rate']:.1f}% [{cell['ci'][0]:.1f}, {cell['ci'][1]:.1f}]"


def write_table(report: dict) -> str:
    out = ["# Phase 4 results", ""]
    s = report.get("screening")
    if s:
        out += ["## The filter alone", "",
                "| Set | Honest blocked (false alarms) | Attacks caught |", "|---|---|---|"]
        for name, key in (("Ordinary honest text (deepset + dolly)", "false_alarms_ordinary"),
                          ("Look-alike honest text (jayavibhav)", "false_alarms_lookalike")):
            out.append(f"| {name} | {s[key]['k']}/{s[key]['n']} = {fmt(s[key])} | |")
        for d, v in s["by_dataset"].items():
            fa, det = v["false_alarms"], v["detection"]
            out.append(f"| {d} | {fa['k']}/{fa['n']} = {fmt(fa) if fa['n'] else '-'} "
                       f"| {det['k']}/{det['n']} = {fmt(det) if det['n'] else '-'} |")
        out += ["", f"Area under the curve: ordinary {s['auc_ordinary']}, look-alike {s['auc_lookalike']}", ""]
    a = report.get("ablation")
    if a:
        out += ["## Ablation (threshold 0.85, 95% ranges from a bootstrap over seeds)", "",
                "| Arm | Cache-caused, saved clean | Cache-caused, saved attack | Script poison served "
                "(saved clean) | Honest hit rate | Hit p50 | Honest blocked |", "|---|---|---|---|---|---|---|"]
        for tag, _ in ARMS:
            arm = a["arms"].get(tag)
            if not arm:
                continue
            c = arm["cells"]
            out.append(f"| {arm['name']} | {fmt(c['secret/clean']['cache_caused'])} "
                       f"| {fmt(c['secret/attack']['cache_caused'])} | {fmt(c['script/clean']['served'])} "
                       f"| {arm['honest_hit_rate']:.1f}% | {arm['hit_p50_ms']} ms "
                       f"| {arm['honest_blocked_at_first_ask']} |")
        out += ["", "Checks: honest questions served the poison, per arm: "
                + ", ".join(f"{t} {arm['controls_served_poison']}/{arm['controls']}"
                            for t, arm in a["arms"].items()), ""]
    load_runs = report.get("load")
    if load_runs:
        out += ["## Load (mock model reply waits 1,900 ms)", "",
                "| Setting | Users | Req/s | Client p50 | Client p99 | Hit p50 | Re-checked hit p50 "
                "| Miss p50 | Overhead p50 | Failures |", "|---|---|---|---|---|---|---|---|---|---|"]
        for tag, _ in LOAD_ARMS:
            for st in load_runs.get(tag, {}).get("steps", []):
                o = st["outcomes"]
                out.append(f"| {load_runs[tag]['name']} | {st['users']} | {st['throughput_rps']} "
                           f"| {st['client_p50_ms']:.0f} ms | {st['client_p99_ms']:.0f} ms "
                           f"| {(o.get('hit') or {}).get('p50')} | {(o.get('rechecked_hit') or {}).get('p50')} "
                           f"| {(o.get('miss') or {}).get('p50')} | {st['overhead_p50_ms']} | {st['failures']} |")
        out.append("")
    return "\n".join(out) + "\n"


def main() -> int:
    report = {"screening": screening_report(), "ablation": ablation_report(),
              "load": load_report(), "earlier": earlier_report()}
    P4.mkdir(parents=True, exist_ok=True)
    (P4 / "report.json").write_text(json.dumps(report, indent=1) + "\n")
    table = write_table(report)
    (P4 / "table.md").write_text(table)
    print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
