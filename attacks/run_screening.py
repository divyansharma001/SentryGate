"""Phase 4: how often does the filter block honest questions, and catch attacks?

Phase 3 saw one false alarm in 100 honest questions. That is too few to say
anything. Here the filter is asked about a larger, held-out set from the same
two public datasets:

    honest    every English honest question in deepset (our 100 controls
              included: the filter is off the shelf, nothing was tuned on them);
              1,000 drawn at random from jayavibhav, whose honest texts are
              synthetic look-alikes full of attack words; and 1,000 everyday
              instructions from databricks-dolly-15k, the closest of the three
              to what ordinary users type
    attacks   every English deepset attack (the 239 seeds' deepset half),
              plus 1,000 jayavibhav attacks not used as seeds

Each text goes through the running gateway in screen_first order, so the
filter always runs and the score comes back in a header. The score is kept,
not just the block decision, so one pass gives the whole curve of catches
against false alarms for every block threshold.

Run against a gateway on real models:

    python attacks/run_screening.py --out data/phase4
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "attacks"))

from generate_variants import download, keep, looks_english, read_rows, unique  # noqa: E402
from run_bypass import INPUTS, http_json, load_jsonl, wait_healthy  # noqa: E402

# A different seed from Week 4, so this draw is independent of the seeds.
RANDOM_SEED = 20261025
JAY_HONEST = 1000
JAY_ATTACKS = 1000
DOLLY_HONEST = 1000


def build_sets() -> list[dict]:
    # download() reuses the Week 4 copy, or fetches it on a fresh clone.
    deepset = (read_rows(download("deepset/prompt-injections", "train"))
               + read_rows(download("deepset/prompt-injections", "test")))
    jay = read_rows(download("jayavibhav/prompt-injection", "test"))
    used = {s["text"] for s in load_jsonl(INPUTS / "seeds.jsonl")}

    rng = random.Random(RANDOM_SEED)
    deepset_honest = unique([t for t, label in deepset if label == 0 and keep(t) and looks_english(t)])
    deepset_attacks = unique([t for t, label in deepset if label == 1 and keep(t) and looks_english(t)])
    jay_honest = rng.sample(unique([t for t, label in jay if label == 0 and keep(t) and t not in used]),
                            JAY_HONEST)
    jay_attacks = rng.sample(unique([t for t, label in jay if label == 1 and keep(t) and t not in used]),
                             JAY_ATTACKS)
    dolly = read_dolly(download_dolly())
    dolly_honest = rng.sample(unique([t for t in dolly if keep(t)]), DOLLY_HONEST)
    rows = []
    for dataset, label, texts in (("deepset", "honest", deepset_honest), ("deepset", "attack", deepset_attacks),
                                  ("jayavibhav", "honest", jay_honest), ("jayavibhav", "attack", jay_attacks),
                                  ("dolly", "honest", dolly_honest)):
        rows += [{"dataset": dataset, "label": label, "text": t} for t in texts]
    return rows


def download_dolly() -> Path:
    """databricks-dolly-15k (CC BY-SA 3.0): 15,000 instructions written by people for ordinary tasks."""
    return download("databricks/databricks-dolly-15k", "train")


def read_dolly(path: Path) -> list[str]:
    import pyarrow.parquet as pq

    return [str(t).strip() for t in pq.read_table(path, columns=["instruction"]).column("instruction").to_pylist()]


def run(base: str, out: Path, limit: int | None) -> dict:
    rows = build_sets()
    if limit:
        rows = rows[:limit // 2] + rows[-limit // 2:]
    # The cache threshold does not change the filter; it is only checked so the
    # gateway is known to be in the configuration the sweep started.
    health = wait_healthy(base, 0.85, "screen_first")
    http_json(f"{base}/v1/cache/clear", {}, "POST")

    results = []
    started = time.time()
    for n, row in enumerate(rows, 1):
        code, headers, _ = http_json(
            f"{base}/v1/chat/completions",
            {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": row["text"]}]}, "POST",
        )
        results.append({"dataset": row["dataset"], "label": row["label"], "chars": len(row["text"]),
                        "status": code, "blocked": code == 403,
                        "score": float(headers.get("x-sentrygate-injection-score", "nan"))})
        if n % 250 == 0 or n == len(rows):
            print(f"  [screening] {n}/{len(rows)}  ({time.time() - started:.0f}s)")

    out.mkdir(parents=True, exist_ok=True)
    with (out / "screening_results.jsonl").open("w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    def rate(label: str, dataset: str | None = None) -> dict:
        group = [r for r in results if r["label"] == label and (dataset is None or r["dataset"] == dataset)]
        blocked = sum(r["blocked"] for r in group)
        return {"n": len(group), "blocked": blocked, "rate": round(blocked / len(group), 4) if group else 0.0}

    summary = {
        "config": health.get("config"),
        "false_alarms": rate("honest"), "detection": rate("attack"),
        "by_dataset": {d: {"false_alarms": rate("honest", d), "detection": rate("attack", d)}
                       for d in ("deepset", "jayavibhav", "dolly")},
    }
    (out / "screening_summary.json").write_text(json.dumps(summary, indent=2))
    fa, det = summary["false_alarms"], summary["detection"]
    print(f"  false alarms {fa['blocked']}/{fa['n']} ({fa['rate']:.1%}), "
          f"attacks caught {det['blocked']}/{det['n']} ({det['rate']:.1%})")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--out", default="data/phase4")
    ap.add_argument("--limit", type=int, default=None, help="a few texts only, for a smoke test")
    args = ap.parse_args()
    run(args.base, ROOT / args.out, args.limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
