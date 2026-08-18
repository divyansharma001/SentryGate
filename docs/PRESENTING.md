# Phase 1 - how to present it

**Window:** 18-22 Aug. **What's being assessed:** the synopsis. No working system is
expected. Your job is to prove the *problem is real* and that you've *scoped the build*.

Everything below is backed by something committed in this repo. Nothing is a claim.

---

## The deck

```bash
make present     # serves it at http://127.0.0.1:8777/deck.html
```

14 slides, built by `docs/build_deck.py` from `docs/deck.template.html`. Every number
on it is parsed out of a real captured run of `poc_bypass.py`, so the slides cannot
drift from what the code prints. Regenerate with `make capture && make deck`.

**Controls:** `->` / `<-` or click to move, **`F`** for full screen, **`N`** for
presenter notes (the talk track below is embedded per-slide).

> Click once inside the deck before using arrow keys - the browser gives the page
> keyboard focus only after a click. In full screen this is not an issue.

Slides 4, 7 and 8 earn the marks (the problem picture, the meters, the three numbers).
Slides 11-13 prove you're not hand-waving. Don't linger on 1 and 3.

---

## The one sentence

> A semantic cache in front of an LLM is an unscreened path to a screened-out response.

If the reviewer remembers one thing, make it that.

---

## Live demo choreography (~60 seconds of talking, 22s of runtime)

**Before you walk in:**
```bash
cd C:\minor-project
make demo          # run it ONCE to warm the OS file cache
```
This matters. First run after a cold boot is slower. Run it once, close the terminal,
reopen it. Also: increase your terminal font size *now*, not on stage.

**On stage:**

1. Type `make demo` and hit enter. It takes ~22s, mostly loading deberta.
   **Talk over the load** — this is your slide-3 moment: *"This loads the same
   injection classifier a real deployment would use — protectai's deberta-v3,
   the current standard. I'm not weakening it."*

2. **Section [1] appears.** Point at it.
   > "The filter works. Score 1.000 on the attack, 0.000 on a benign prompt.
   > No false positive. This is not a story about a bad filter."

3. **Section [2].** One line.
   > "One poisoned entry in the cache. However it got there — a prompt that scored
   > just under threshold, a pre-deployment cache warm, a shared tenant."

4. **Section [3].** This is the reveal. Point at the `inj` column.
   > "Ten attack variants. The filter scores **every single one** at 1.000 —
   > including the full rewrites at the bottom. It catches all ten."
   
   Then slide your finger to the `sim` column.
   > "But look at the top five. Cosine 0.92 to 0.99. Those are cache **hits**."

5. **Section [4].** The kill shot. Point at the last line.
   > "Five attacks served from the poisoned entry. **Filter invocations: zero.**
   > It would have caught all of them. It was never asked."

6. **Section [5].** The sweep.
   > "And this holds across every threshold anyone actually deploys."

7. Stop talking. Let it sit for two seconds. Then go to slide 6 (the fix).

---

## The result, in numbers

```
             sim     inj    @0.85
surface    0.919-0.993   1.000    HIT   x5    <- casing / punctuation / filler
rewrite    0.224-0.709   1.000   miss   x5    <- full paraphrase
control   -0.018         0.000   miss         <- "what is the capital of France?"

filter would catch:  10/10
served from cache:    5/10
filter invocations:   0
```

Threshold sweep:

| threshold | surface | rewrite | overall |
|---|---|---|---|
| 0.95 | 40% | 0% | 20% |
| 0.90 | 100% | 0% | 50% |
| **0.85** | **100%** | **0%** | **50%** |
| 0.75 | 100% | 0% | 50% |
| 0.65 | 100% | 40% | 70% |

**The line to deliver:** the variants that get through are the *cheapest* ones —
casing, punctuation, an inserted "all". An attacker doesn't need a paraphrase model.
They need a shift key.

Note 0.85 is a *conservative* setting. Typical deployments run 0.75–0.80, where it's
still 50%. You are not tuning the threshold to make the result look good, and you
should say so — a reviewer will wonder.

---

## Questions you will get, and the answers

**"Isn't this just a badly configured cache?"**
No — the bypass holds from 0.65 all the way to 0.90. There's no threshold that keeps
the cache useful and closes the hole. Raise it to 0.95 and you still leak 40% of
surface mutations while destroying your hit ratio. That trade-off curve is exactly
what Phase 3 Week 2 measures.

**"Why not just run the filter on cache hits too?"**
That's a real option and I'm implementing it — but as a *targeted* one, in Phase 3
Week 2, only for high-risk intents. Running the classifier on every hit costs you the
entire latency win that justified the cache: ~15ms becomes ~100ms+. The contribution
is doing it *selectively*, driven by the stored verdict. And the ablation in Phase 4
Week 2 measures what that choice actually buys.

**"How did the poisoned entry get in the cache?"**
Three realistic paths: a prompt scoring just under threshold, a cache warmed before
the filter was deployed, or a multi-tenant cache where another tenant's traffic
populated it. Phase 2 Week 4 implements the first one end to end on the real gateway.

**"Is the filter you used any good?"**
It's `protectai/deberta-v3-base-prompt-injection-v2`, the current off-the-shelf
standard, unmodified, and it scored 1.000 on all ten variants. Using a *better* filter
makes my point stronger, not weaker — the gap isn't detection quality, it's that
detection is never invoked.

**"What's actually novel here?"**
Storing the security verdict in the vector payload so retrieval itself is
verdict-filtered. Caches filter on similarity; nobody filters on security state. That
turns the filter from something you call into something the retrieval predicate
enforces.

**"Is this only your PoC, or does it affect real systems?"**
Right now it's a controlled PoC — I'm not claiming a CVE. Phase 2 Week 4 reproduces
it on a real gateway with real datasets (`deepset/prompt-injections`,
`jayavibhav/prompt-injection`) and produces a bypass rate on the full attack corpus.

---

## Failure plan

| If | Then |
|---|---|
| Model cache is broken / wifi is down | `make demo-fast` — keyword filter, ~5s, **identical numbers**. Already tested. |
| Laptop won't cooperate at all | Screen-record `make demo` tonight. Put the MP4 in the deck on slide 4. |
| You're short on time | Skip sections [3] and [5]. Sections [1], [2], [4] are the whole argument. |
| Projector is low-res | Terminal font 18pt+. The summary block at the bottom is self-contained — it restates everything. |

**Record the fallback video tonight.** It costs you five minutes and removes the only
real risk in this presentation.

---

## What to say about the code being small

A reviewer may note it's one script. Get ahead of it on slide 8:

> "Phase 1 is the synopsis eval, so the deliverable is the *argument*, not the system.
> This script exists to make the vulnerability concrete rather than asserted. The
> repo layout on this slide is the build plan, and Phase 2 starts the gateway on the
> 23rd."

That reframes "small" as "scoped", which is what it is.
