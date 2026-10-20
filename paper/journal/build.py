"""Build the journal paper: paper/journal/SentryGate-journal.pdf.

The source is paper.html plus the fragments in parts/. Every {{token}} in
them is either a fragment (parts/<token>.html, diagrams/<token>.svg) or a
number computed here from the committed result files. Nothing is typed in by
hand, and the build stops if any token is left without a value.

Needs Google Chrome (prints the page to PDF) and the figures from
make_figures.py. Run:  make journal
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = HERE / "build"
OUTPUT = HERE / "SentryGate-journal.pdf"
TOKEN = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")


def read(path: str) -> dict:
    return json.loads((ROOT / path).read_text())


def jsonl(path: str) -> list[dict]:
    return [json.loads(line) for line in (ROOT / path).read_text().splitlines() if line.strip()]


def f1(x: float) -> str:
    return f"{x:.1f}"


def ci(cell: dict) -> str:
    return f"{cell['ci'][0]:.1f}&ndash;{cell['ci'][1]:.1f}"


def thousands(n: int) -> str:
    return f"{n:,}"


def pin(requirements: str, name: str) -> str:
    for line in (ROOT / requirements).read_text().splitlines():
        if line.lower().startswith(name.lower() + "=="):
            return line.split("==", 1)[1].strip()
    raise SystemExit(f"{name} is not pinned in {requirements}")


def torch_pin() -> str:
    m = re.search(r"torch==([0-9.]+)", (ROOT / "deploy" / "Dockerfile.gateway").read_text())
    if not m:
        raise SystemExit("torch is not pinned in deploy/Dockerfile.gateway")
    return m.group(1)


def count_tests() -> int:
    """Tests pytest actually collects, written by make journal (parametrised cases count once each)."""
    path = BUILD / "tests.txt"
    if not path.exists():
        raise SystemExit("Run make journal: it records the test count from pytest first.")
    m = re.search(r"(\d+) tests? collected", path.read_text())
    if not m:
        raise SystemExit(f"No test count in {path}")
    return int(m.group(1))


def values() -> dict[str, str]:
    w4 = read("data/week4/report.json")
    manifest = read("data/week4/manifest.json")
    p3 = read("data/phase3/report.json")
    p4 = read("data/phase4/report.json")
    router = read("data/router/report.json")
    env = read("paper/journal/environment.json")
    seeds = jsonl("data/week4/seeds.jsonl")
    sweep = p4["earlier"]["bypass_by_threshold"]
    ranges = p4["earlier"]["phase3_cache_caused"]
    v: dict[str, str] = {}

    # Corpus.
    v["n_seeds"] = str(w4["seeds"])
    v["n_seeds_deepset"] = str(sum(1 for s in seeds if s["dataset"] == "deepset"))
    v["n_seeds_jay"] = str(sum(1 for s in seeds if s["dataset"] == "jayavibhav"))
    v["n_variants"] = thousands(w4["attack_variants_per_threshold"])
    v["n_lazy"] = thousands(manifest["counts"]["lazy"])
    v["n_rewrite"] = thousands(manifest["counts"]["rewrite"])
    v["n_controls"] = str(manifest["counts"]["controls"])

    # E1: the threshold sweep.
    for t in sweep:
        key = t.replace("0.", "").ljust(2, "0")
        for fam in ("lazy", "rewrite", "all"):
            v[f"w4_{fam}_{key}"] = f1(sweep[t][fam]["rate"])
            v[f"w4_{fam}_{key}_ci"] = ci(sweep[t][fam])
    v["w4_lazy_085"] = v["w4_lazy_85"]
    v["w4_lazy_drop"] = f1(sweep["0.85"]["lazy"]["rate"] - sweep["0.95"]["lazy"]["rate"])
    # The gateway's own cheap label, applied to the seeds.
    sys.path.insert(0, str(ROOT))
    from app.verdict import classify_intent

    v["n_seeds_risky"] = str(sum(1 for s in seeds if classify_intent(s["text"]) in ("credentials", "tool_use", "pii")))
    v["w4_confirmed"] = thousands(w4["confirmed_bypasses_have_zero_screening"])
    v["w4_exact"] = w4["exact_served"].replace("/", " of ")
    v["w4_controls"] = w4["control_served_poison"].replace("/", " of ")
    v["w4_mismatch"] = str(w4["score_hit_mismatches"])

    # E2: the filter-first order, and the filter asked directly.
    w4rows = [r for r in jsonl("data/week4/results.jsonl") if r["tag"] == "screen_first" and r["family"] != "exact"]
    blocked = sum(r["status"] == 403 for r in w4rows)
    v["e2_blocked_pct"] = f1(100 * blocked / len(w4rows))
    v["e2_served_pct"] = f1(100 * sum(r["served_poison"] for r in w4rows) / len(w4rows))
    for ds in ("deepset", "jayavibhav"):
        rows = [r for r in w4rows if r["dataset"] == ds]
        v[f"e2_blocked_{ds}"] = f1(100 * sum(r["status"] == 403 for r in rows) / len(rows))

    # E3: the defence settings.
    for tag in ("base", "filter", "recheck", "both", "all"):
        arm = p3["arms"][tag]
        for label in ("clean", "attack"):
            v[f"p3_{tag}_{label}"] = f1(arm["served"][label]["cache_caused"])
            v[f"p3_{tag}_{label}_ci"] = ci(ranges[f"{tag}/{label}"])
            v[f"p3_{tag}_{label}_miss"] = f1(arm["served"][label]["filter_miss"])
        v[f"p3_{tag}_hits"] = f1(arm["honest_hit_rate"])
        v[f"p3_{tag}_hit_ms"] = f"{arm['hit_p50_ms']:.0f}"
        v[f"p3_{tag}_miss_ms"] = f"{arm['miss_p50_ms']:.0f}"
    v["recheck_extra_ms"] = f"{p3['arms']['all']['hit_p50_ms'] - p3['arms']['base']['hit_p50_ms']:.0f}"
    v["p3_all_upper"] = f"{ranges['all/clean']['ci'][1]:.1f}"
    v["p3_honest_n"] = str(p3["honest_questions"])

    # E7: the model picker.
    v["r_saved_easy"] = f"{100 * (1 - router['cost_by_label']['easy']['router'] / router['cost_by_label']['easy']['strong']):.0f}"
    v["r_saved_hard"] = f"{100 * (1 - router['cost_by_label']['hard']['router'] / router['cost_by_label']['hard']['strong']):.0f}"
    v["r_saved_all"] = f"{router['saved_pct']:.0f}"
    v["r_agree"] = str(router["agrees_with_our_label"])
    v["r_questions"] = str(router["questions"])
    v["r_cheap_ms"] = thousands(router["model_ms_p50"]["cheap"])
    v["r_strong_ms"] = thousands(router["model_ms_p50"]["strong"])
    v["r_mix80"] = f"{router['projected_saving_by_mix']['80% easy']:.0f}"
    v["r_mix90"] = f"{router['projected_saving_by_mix']['90% easy']:.0f}"
    v["r_cost_router"] = f"{router['router_cost_usd']:.4f}"
    v["r_cost_strong"] = f"{router['strong_cost_usd']:.4f}"
    for lab in ("easy", "hard"):
        for arm in ("router", "strong"):
            v[f"r_{lab}_{arm}"] = f"{router['cost_by_label'][lab][arm]:.5f}"

    # Phase 4: filled in only once the runs exist.
    v.update(phase4_values(p4))

    # Environment, from the build machine record and the pinned versions.
    v.update({k: str(val) for k, val in env.items()})
    v["torch_version"] = torch_pin()
    v["st_version"] = pin("requirements-gateway.txt", "sentence-transformers")
    v["qdrant_version"] = re.search(r"qdrant/qdrant:v([0-9.]+)", (ROOT / "docker-compose.yml").read_text()).group(1)
    v["locust_version"] = pin("requirements-attacks.txt", "locust")
    v["n_tests"] = str(count_tests())
    return v


def phase4_values(p4: dict) -> dict[str, str]:
    v: dict[str, str] = {}
    s = p4.get("screening") or {}
    if s:
        v["scr_honest_n"] = thousands(s["false_alarms"]["n"])
        v["scr_attack_n"] = thousands(s["detection"]["n"])
        for key, name in (("false_alarms_ordinary", "ord"), ("false_alarms_lookalike", "look")):
            v[f"scr_fa_{name}"] = f1(s[key]["rate"])
            v[f"scr_fa_{name}_ci"] = ci(s[key])
            v[f"scr_fa_{name}_k"] = str(s[key]["k"])
            v[f"scr_fa_{name}_n"] = thousands(s[key]["n"])
        v["scr_det"] = f1(s["detection"]["rate"])
        v["scr_det_ci"] = ci(s["detection"])
        v["scr_auc_ord"] = f"{s['auc_ordinary']:.3f}"
        v["scr_auc_look"] = f"{s['auc_lookalike']:.3f}"
        for d, dv in s["by_dataset"].items():
            v[f"scr_{d}_fa"] = f1(dv["false_alarms"]["rate"])
            v[f"scr_{d}_fa_ci"] = ci(dv["false_alarms"])
            v[f"scr_{d}_fa_k"] = str(dv["false_alarms"]["k"])
            v[f"scr_{d}_fa_n"] = thousands(dv["false_alarms"]["n"])
            v[f"scr_{d}_det"] = f1(dv["detection"]["rate"])
            v[f"scr_{d}_det_ci"] = ci(dv["detection"])
            v[f"scr_{d}_det_n"] = thousands(dv["detection"]["n"])
        for point in s["curve"]:
            key = str(point["threshold"]).replace(".", "")
            v[f"scr_curve_fa_ord_{key}"] = f1(point["false_alarm_ordinary"])
            v[f"scr_curve_fa_look_{key}"] = f1(point["false_alarm_lookalike"])
            v[f"scr_curve_det_{key}"] = f1(point["detection"])
    a = (p4.get("ablation") or {}).get("arms") or {}
    for tag, arm in a.items():
        for cell, c in arm["cells"].items():
            k = cell.replace("/", "_")
            for measure in ("served", "cache_caused", "filter_miss"):
                v[f"ab_{tag}_{k}_{measure}"] = f1(c[measure]["rate"])
                v[f"ab_{tag}_{k}_{measure}_ci"] = ci(c[measure])
            v[f"ab_{tag}_{k}_guard"] = str(c["guard_blocked"])
        v[f"ab_{tag}_hits"] = f1(arm["honest_hit_rate"])
        v[f"ab_{tag}_hit_ms"] = f"{arm['hit_p50_ms']:.0f}" if arm["hit_p50_ms"] is not None else "n/a"
        v[f"ab_{tag}_hit_p99"] = f"{arm['hit_p99_ms']:.0f}" if arm["hit_p99_ms"] is not None else "n/a"
        v[f"ab_{tag}_blocked"] = str(arm["honest_blocked_at_first_ask"])
        v[f"ab_{tag}_controls"] = f"{arm['controls_served_poison']} of {arm['controls']}"
    loads = p4.get("load") or {}
    users = sorted({st["users"] for run in loads.values() for st in run["steps"]})
    if users:
        v["load_max_users"] = str(max(users))
    for tag, run in loads.items():
        for st in run["steps"]:
            u = st["users"]
            v[f"ld_{tag}_{u}_rps"] = f"{st['throughput_rps']:.1f}"
            v[f"ld_{tag}_{u}_p50"] = f"{st['client_p50_ms']:.0f}"
            v[f"ld_{tag}_{u}_p99"] = f"{st['client_p99_ms']:.0f}"
            v[f"ld_{tag}_{u}_fail"] = str(st["failures"])
            v[f"ld_{tag}_{u}_n"] = thousands(st["requests"])
            v[f"ld_{tag}_{u}_ovh"] = f"{st['overhead_p50_ms']:.0f}" if st["overhead_p50_ms"] is not None else "n/a"
            for kind, o in st["outcomes"].items():
                for q in ("p50", "p95", "p99"):
                    v[f"ld_{tag}_{u}_{kind}_{q}"] = f"{o[q]:.0f}" if o[q] is not None else "n/a"
                v[f"ld_{tag}_{u}_{kind}_n"] = thousands(o["n"])
    return v


def fragment(name: str) -> str | None:
    for path in (HERE / "parts" / f"{name}.html", HERE / "diagrams" / f"{name.removeprefix('svg_')}.svg"):
        if path.exists():
            text = path.read_text()
            if path.suffix == ".svg":
                # Inline, without the XML prolog, so the page's fonts apply.
                text = re.sub(r"^<\?xml[^>]*>\s*", "", text)
            return text
    return None


def render(v: dict[str, str]) -> str:
    text = (HERE / "paper.html").read_text()
    for _ in range(10):
        missing = set()

        def sub(match: re.Match) -> str:
            name = match.group(1)
            if name in v:
                return v[name]
            frag = fragment(name)
            if frag is not None:
                return frag
            missing.add(name)
            return match.group(0)

        new = TOKEN.sub(sub, text)
        if new == text:
            break
        text = new
    left = sorted(set(TOKEN.findall(text)))
    if left and "--draft" in sys.argv:
        # Layout check only: mark each missing value in red. Never shipped.
        print("draft: no value yet for " + ", ".join(left))
        return TOKEN.sub(lambda m: f'<span style="color:#c00">[{m.group(1)}]</span>', text)
    if left:
        raise SystemExit("No value for: " + ", ".join(left))
    return text


def find_chrome() -> str:
    for c in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome") or "", shutil.which("chromium") or ""):
        if c and Path(c).exists():
            return c
    raise SystemExit("Needs Google Chrome to print the PDF. Set CHROME=/path/to/chrome.")


def main() -> int:
    html = render(values())
    BUILD.mkdir(exist_ok=True)
    page = BUILD / "paper.html"
    page.write_text(html.replace('src="figures/', 'src="../figures/'))
    if "--draft" in sys.argv:
        OUTPUT_DRAFT = BUILD / "draft.pdf"
        chrome = os.environ.get("CHROME") or find_chrome()
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--allow-file-access-from-files", f"--print-to-pdf={OUTPUT_DRAFT}", page.as_uri()],
                       check=True, capture_output=True, timeout=120)
        print(f"wrote {OUTPUT_DRAFT}")
        return 0
    if "--html" in sys.argv:
        print(f"wrote {page}")
        return 0
    chrome = os.environ.get("CHROME") or find_chrome()
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--allow-file-access-from-files", f"--print-to-pdf={OUTPUT}", page.as_uri()],
                   check=True, capture_output=True, timeout=120)
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
