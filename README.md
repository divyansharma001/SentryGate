# SentryGate

Code, data and paper source for:

**Measuring and Closing a Semantic-Cache Bypass of Prompt-Injection Filters in Large Language Model Gateways**

Divyansh Sharma, Yashvit Gauri, Sarvagya Dabas, Sandeep Singh.
The paper is under review.
The current PDF is [`paper/journal/SentryGate-journal.pdf`](paper/journal/SentryGate-journal.pdf).

## The problem

Most products built on a large language model put two things in front of the model:

- a **safety filter** that scores each prompt and blocks prompt-injection attacks, and
- a **semantic cache** that returns a stored answer when a new prompt is close in meaning to an old one.

The cache is checked first, because the filter is slow and the cache is fast.
So on a cache hit the filter is never asked.
A harmful answer that is already in the cache can be collected by anyone who sends a prompt that looks similar enough.

## What we found

SentryGate is an OpenAI-compatible gateway built from real parts: a DeBERTa-v3 injection classifier, MiniLM embeddings, Qdrant and Redis.
We measured the problem on it with 2,838 rewordings of 239 public attacks.

| Question | Result |
|---|---|
| Do reworded attacks get the poisoned answer unscreened? | 97.3% of lazy edits at a cache threshold of 0.85, and 90.0% at 0.95 |
| Is the order the cause? | Yes. With the filter in front of the cache, the bypass rate is zero |
| Does matching on the stored verdict fix it? | No. It left 47.0% of cache-caused leaks when the poison was stored as clean |
| What does fix it? | Re-checking every cache hit: 0 of 2,838 cache-caused leaks (95% upper bound 1.3%) |
| What does the fix cost? | About 89 ms per hit. Honest users kept 95.0% of their cache hits |

Every counted bypass is backed by the gateway's own log line saying the filter did not run.

## What is in this repository

| Path | What it holds |
|---|---|
| `app/` | The gateway: cache, filter, verdict, model picker, output guard, rate limits, request log |
| `attacks/` | The attack tools and the scripts that run each experiment |
| `eval/` | The scripts that turn results into tables and figures |
| `tests/` | The test suite (93 tests, no network or model download needed) |
| `data/` | The attack set, the per-request results of every experiment, and recorded model replies |
| `paper/journal/` | The paper: source, figures, build scripts and the PDF |
| `paper/figures/` | Earlier charts drawn by `eval/` |
| `docs/` | Architecture diagrams and recorded demo output |
| `deploy/`, `docker-compose.yml` | Container images and services |
| `poc_bypass.py` | The first offline proof of concept |

The raw gateway logs of the sweeps (`data/*/run-*.jsonl`, over 40 MB) are not committed.
The per-request result files and the summaries built from them are.

## Quick start

You need Docker.
No API key and no account are needed.
The gateway starts in mock mode.

```bash
make gateway-up      # nginx + gateway on http://127.0.0.1:8080
make gateway-smoke   # health check, one request, and the log line it wrote
make gateway-test    # run the test suite inside the image
make gateway-down
```

Every reply says what happened in its headers:

```
x-sentrygate-cache:    hit
x-sentrygate-screened: false
x-sentrygate-provider: cache
```

The first offline proof of concept runs on its own:

```bash
docker compose build poc      # once, a few minutes, needs internet
docker compose run --rm poc   # a few seconds, no internet
```

## Reproduce the results

Rebuild the tables, figures and paper from the committed result files.
These finish in seconds to minutes.

| Command | What it rebuilds |
|---|---|
| `make figures` | The bypass table and chart (`data/week4/table.md`) |
| `make defence-figures` | The defence table and charts (`data/phase3/table.md`) |
| `make phase4-report` | Confidence intervals and the filter-alone tables (`data/phase4/table.md`) |
| `make journal-figures` | Every data figure of the paper |
| `make journal` | The paper PDF, with every number filled in from the result files (needs Google Chrome) |

Run the experiments again on the real gateway.
These take from minutes to a few hours.

| Command | Experiment |
|---|---|
| `make variants` | Regenerate the attack rewordings from the public datasets |
| `make bypass` | E1 and E2: the bypass across seven cache thresholds, and the filter-first order |
| `make defence` | E3: the five defence settings |
| `make phase4` | E4: the filter on its own, on texts it was not tuned on |
| `bash attacks/router_live.sh` | E5: the model picker on live calls (needs an API key, costs about $0.20) |
| `bash attacks/mitigations_demo.sh` | The output guard and the rate limiter, live and free |

Result tables:
[`data/week4/table.md`](data/week4/table.md),
[`data/phase3/table.md`](data/phase3/table.md),
[`data/phase4/table.md`](data/phase4/table.md),
[`data/router/table.md`](data/router/table.md),
[`data/mitigations/demo.txt`](data/mitigations/demo.txt).

## Settings

The vulnerable baseline and every defended setting are the same program.
Each layer is one environment variable, read once at start-up and copied into every log line.
The defaults are the vulnerable baseline.

| Switch | Default | Meaning |
|---|---|---|
| `PIPELINE_ORDER` | `cache_first` | `screen_first` runs the filter before the cache |
| `SIM_THRESHOLD` | `0.85` | Similarity a stored prompt needs to count as a hit |
| `CACHE_VERDICT_FILTER` | `off` | Search only entries whose stored verdict and label fit the request |
| `CACHE_REVERIFY_HIGH_RISK` | `off` | Run the filter again on a cache hit |
| `REVERIFY_SCOPE` | `risky` | `all` re-checks every hit. This is the safe setting |
| `OUTPUT_GUARD` | `off` | `flag` or `block` answers that carry script, SQL, shell or secrets |
| `RATE_LIMIT_RPM` | `0` | Requests per minute for one caller. `0` means no limit |
| `ROUTER_MODE` | `fixed` | `difficulty` sends easy questions to a cheaper model |
| `PROVIDER_MODE` | `mock` | `replay` uses recorded replies, `live` calls a real model |

The full list is in [`app/config.py`](app/config.py).
Copy `.env.example` to `.env` only if you want live model calls.
`.env` is ignored by git.

## Tests and code checks

```bash
make gateway-test   # 93 tests
make lint           # ruff, pinned version
```

## Limits

- The attack experiments mock the model reply, because a cached answer never reaches the model. The filter, the embedder and the stores are real.
- All results use one injection classifier and one embedding model. Other parts will give other rates.
- The poisoned answer is planted directly. Pre-filled and shared caches are discussed in the paper but not measured.
- Response times come from one laptop.

The paper lists these in full.

## Licence

The code is under the MIT licence, see [`LICENSE`](LICENSE).
The attack texts in `data/` are derived from two public datasets, `deepset/prompt-injections` and `jayavibhav/prompt-injection`.
They stay under the terms of those datasets.
