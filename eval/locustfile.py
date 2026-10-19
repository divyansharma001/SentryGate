"""Phase 4 load test: a mixed trace of traffic, replayed at rising load.

Each simulated user loops over three kinds of request, in fixed shares:

    repeat  60%  one of 100 honest questions, or a lazy rewording of one.
                 The sweep asks every one once before the run, so these
                 are cache hits: the traffic a cache exists for.
    new     25%  an honest question never seen before (drawn from the
                 jayavibhav honest pool). Always a miss: screened, then the
                 model is called. With MOCK_LATENCY_MS set, the mock reply
                 waits as long as a real one.
    attack  15%  a reworded attack from the Week 4 set. Blocked, or served
                 from the cache if it matches something honest.

Every request is named by its kind, so Locust reports each kind apart. The
gateway's own log says what actually happened to each request (hit, miss,
re-checked hit, blocked), which is what the report reads.

Run by attacks/sweep_phase4.sh, never by hand:

    locust -f eval/locustfile.py --headless -u 10 -r 10 -t 60s --host http://127.0.0.1:8080
"""

from __future__ import annotations

import itertools
import json
import random
import sys
from pathlib import Path

from locust import HttpUser, constant, task

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "attacks"))

from generate_variants import LAZY_EDITS, download, keep, read_rows, unique  # noqa: E402

TRACE_SEED = 20261101


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def hot_questions() -> list[str]:
    """The 100 honest controls and their lazy rewordings. The sweep warms the cache with the controls."""
    controls = [c["text"] for c in _jsonl(ROOT / "data" / "week4" / "controls.jsonl")]
    return unique(controls + [edit(t) for t in controls for _, edit in LAZY_EDITS])


def new_questions() -> list[str]:
    used = {c["text"] for c in _jsonl(ROOT / "data" / "week4" / "controls.jsonl")}
    pool = unique([t for t, label in read_rows(download("jayavibhav/prompt-injection", "test"))
                   if label == 0 and keep(t) and t not in used])
    random.Random(TRACE_SEED).shuffle(pool)
    return pool


HOT = hot_questions()
NEW = itertools.cycle(new_questions())
ATTACKS = [v["text"] for v in _jsonl(ROOT / "data" / "week4" / "variants.jsonl") if v["family"] != "exact"]
RNG = random.Random(TRACE_SEED)


def body(text: str) -> dict:
    return {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": text}]}


class TraceUser(HttpUser):
    # No think time: each user sends its next request as soon as the last returns,
    # so the user count is the number of requests in flight.
    wait_time = constant(0)

    def _send(self, kind: str, text: str) -> None:
        # Each user is its own caller, as separate apps would be.
        headers = {"authorization": f"Bearer load-user-{id(self) % 100000}"}
        with self.client.post("/v1/chat/completions", json=body(text), headers=headers,
                              name=kind, catch_response=True) as r:
            # A blocked attack is the gateway working, not a failure.
            if r.status_code in (200, 403):
                r.success()
            else:
                r.failure(f"status {r.status_code}")

    @task(60)
    def repeat(self) -> None:
        self._send("repeat", RNG.choice(HOT))

    @task(25)
    def new(self) -> None:
        self._send("new", next(NEW))

    @task(15)
    def attack(self) -> None:
        self._send("attack", RNG.choice(ATTACKS))
