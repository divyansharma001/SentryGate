# SentryGate

A security gateway for LLM APIs. The thesis in one line:

> **A semantic cache in front of an LLM is an unscreened path to a screened-out
> response.** SentryGate closes it by computing the security verdict once at
> screening and storing it in the Qdrant payload, so cache lookups become
> *verdict-filtered* searches — the filter *is* the retrieval predicate.

Plan of record: [`specs/001-introfile.md`](specs/001-introfile.md).
Architecture: [`docs/architecture.mmd`](docs/architecture.mmd) (regenerated each phase).

## Status

| Phase | Window | State |
|---|---|---|
| 1 — Synopsis / 1st presentation | 18–22 Aug | **in progress** — `poc_bypass.py` done |
| 2 — Progress Eval-1 (gateway + baseline cache + bypass reproduced) | 23 Aug – 26 Sep | not started |
| 3 — Progress Eval-2 (verdict-tagged cache, routing, 2 mitigations) | 27 Sep – 24 Oct | not started |
| 4 — Final (eval suite, ablation, paper) | 25 Oct – 14 Nov | not started |

## Phase 1 — run the proof of concept

```bash
py -3.11 -m venv .venv
./.venv/Scripts/python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
./.venv/Scripts/python.exe -m pip install -r requirements-poc.txt

make poc          # real protectai/deberta-v3 filter (~370MB on first run)
make poc-fast     # keyword stand-in, no download — use this if the venue wifi is bad
```

The script establishes, in five steps:

1. **The filter is not the weak point.** deberta scores the raw attack
   `1.000 INJECTION` and the benign control `0.000` - no false positive.
2. The cache holds **one** poisoned entry keyed on that attack.
3. Ten attack variants are scored *both* ways - by the filter and by the cache.
   The filter flags **10/10 at score 1.000**, including full rewrites.
4. Five of them are served straight from the poisoned entry, with the filter
   invocation counter at **0**. A cache hit returns before screening.
5. A threshold sweep shows the shape of the finding.

### Measured result (threshold 0.85, deliberately conservative)

```
 thresh   surface   rewrite   overall
   0.95       40%        0%       20%
   0.90      100%        0%       50%
   0.85      100%        0%       50%   <- 5/10 served, 0 filter calls
   0.75      100%        0%       50%
   0.65      100%       40%       70%
```

**The finding that matters:** the variants that bypass are the *cheapest* ones -
casing, punctuation, an inserted `all`/`your`/`please`. Those sit at cosine
0.92-0.99 and clear every deployed threshold. Full paraphrases (no shared
vocabulary) land at 0.22-0.71 and mostly miss. An attacker needs no paraphrase
model at all; they need a shift key.

> Note: the spec's 25-line sketch assumed a single paraphrase would clear 0.75.
> Measured, that paraphrase scores **0.474** - the sketch as written prints
> `miss` and the live demo would have fallen flat. The surface/rewrite split
> above is what actually reproduces.

## Run it in Docker

No Python setup, no venv. The models are baked into the image, so it runs
with the network switched off.

```bash
docker compose build poc
docker compose run --rm poc          # real filter, ~22s
docker compose run --rm poc --fast   # keyword stand-in, ~5s
```

The `poc` service is declared with `network_mode: none`, which proves the demo
has no hidden internet dependency - it physically cannot reach the network.

`qdrant` and `redis` are declared too, behind a `phase2` profile, because
Phase 2 needs them and they are plain images with no code required:

```bash
docker compose --profile phase2 up -d qdrant redis
```

## Why there are no API keys anywhere

Phase 1 makes **zero calls to any LLM provider**. Both models run locally:

| Model | Job | Size |
|---|---|---|
| `all-MiniLM-L6-v2` | turns a sentence into 384 numbers, so the cache can compare meanings | ~90 MB |
| `protectai/deberta-v3-base-prompt-injection-v2` | scores how much a prompt looks like an attack | ~370 MB |

Neither is a chat model, so neither needs a key. The "answer" in the cache is a
hard-coded string - we never needed a real model to generate one, because the
experiment is about *retrieval*, not generation.

Real OpenAI/Anthropic keys are first needed in **Phase 2 Week 1**, when the
gateway starts calling a real model on a cache miss. Copy `.env.example` to
`.env` at that point; `.env` is gitignored and git refuses to stage it.

## Environment notes

- **Python 3.11**, not the 3.14 that is first on `PATH` here. Presidio/spaCy and
  several torch builds have no 3.14 wheels yet.
- **CPU-only torch.** The 4GB GTX 1650 on this machine is not needed for MiniLM
  or deberta-base, and the Docker gateway will run CPU anyway.
