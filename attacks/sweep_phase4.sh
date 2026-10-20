#!/usr/bin/env bash
# The Phase 4 evaluation. Three parts, each can run on its own:
#
#   screening   the filter alone, on ~2,800 held-out honest and attack texts:
#               false alarms, catches, and the score behind each
#   ablation    the full system, then one layer switched off at a time, against
#               the same 2,838 attack rewordings and 99 honest questions
#   load        a mixed trace replayed with Locust at 1 to 50 users, through
#               nginx, for the open baseline and the full defence
#
# Real models, PROVIDER_MODE=mock (no money spent), HF_HUB_OFFLINE=1.
# The gateway is capped at GATEWAY_CPUS cores (default 3) for every arm.
# The load test sets MOCK_LATENCY_MS=1900, the measured median of a real
# cheap-model answer (data/router/report.json), so a miss takes as long as one.
#
# Usage:  bash attacks/sweep_phase4.sh [all|screening|ablation|load] [LIMIT]
set -euo pipefail
cd "$(dirname "$0")/.."

PART="${1:-all}"
LIMIT="${2:-}"
LIMIT_ARG=""
[ -n "$LIMIT" ] && LIMIT_ARG="--limit $LIMIT"
OUT=data/phase4
GW=http://127.0.0.1:8000
BUILD_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
LOAD_USERS="${LOAD_USERS:-1 5 10 25 50}"
LOAD_SECONDS="${LOAD_SECONDS:-60}"
# Cores the gateway may use. Kept low so the laptop running the sweep stays
# usable; every arm and the load test get the same cap, so they compare fairly.
GATEWAY_CPUS="${GATEWAY_CPUS:-3}"

export BUILD_SHA PROVIDER_MODE=mock PROVIDER_RECORD=off SIM_THRESHOLD=0.85 \
       CACHE_STRICT_THRESHOLD=0.95 REVERIFY_SCORE=0.2 INJECTION_THRESHOLD=0.5 \
       SCREENING_SCORER=hf CACHE_EMBEDDER=hf CACHE_BACKEND=auto EMBED_MODEL=all-MiniLM-L6-v2 \
       ALLOW_CACHE_SEED=on HF_HUB_OFFLINE=1 RATE_LIMIT_RPM=0 TOKEN_BUDGET_PER_DAY=0 \
       REDIS_HOST_PORT="${REDIS_HOST_PORT:-6380}"

docker compose --profile phase2 up -d qdrant redis >/dev/null
mkdir -p "$OUT"

# order, screening, verdict_filter, reverify, scope, guard, latency_ms, logfile
start_gateway() {
    PIPELINE_ORDER="$1" SCREENING="$2" CACHE_VERDICT_FILTER="$3" CACHE_REVERIFY_HIGH_RISK="$4" \
    REVERIFY_SCOPE="$5" OUTPUT_GUARD="$6" MOCK_LATENCY_MS="$7" LOG_FILE="$8" \
        docker compose up -d --force-recreate gateway nginx >/dev/null 2>&1
    docker update --cpus "$GATEWAY_CPUS" sentrygate-gateway >/dev/null
    for _ in $(seq 1 90); do
        curl -sf "$GW/healthz" >/dev/null 2>&1 && return 0
        sleep 3
    done
    echo "Gateway did not come up for $8" >&2
    docker logs --tail 20 sentrygate-gateway >&2
    exit 1
}

in_attacks() {
    docker run --rm --network container:sentrygate-gateway -v "$PWD":/src -w /src sentrygate-attacks "$@"
}

run_screening() {
    echo "Screening: false alarms and catches."
    start_gateway screen_first on off off risky off 0 phase4/run-screening.jsonl
    in_attacks python attacks/run_screening.py --out "$OUT" $LIMIT_ARG
}

run_ablation() {
    echo "Ablation: the full system, then one layer off at a time."
    rm -f "$OUT"/results.jsonl "$OUT"/summary.jsonl "$OUT"/controls_results.jsonl \
          "$OUT"/benign_results.jsonl "$OUT"/benign_summary.jsonl
    # tag  order  screening  verdict_filter  reverify  scope  guard
    for arm in "full         cache_first  on  on  on  all    block" \
               "no_recheck   cache_first  on  on  off all    block" \
               "no_label     cache_first  on  off on  all    block" \
               "no_guard     cache_first  on  on  on  all    off" \
               "no_screening cache_first  off on  on  all    block" \
               "none         cache_first  on  off off risky  off" \
               "safe_order   screen_first on  off off risky  off"; do
        set -- $arm
        tag=$1; order=$2; scr=$3; vf=$4; rv=$5; scope=$6; guard=$7
        echo "Arm $tag:"
        start_gateway "$order" "$scr" "$vf" "$rv" "$scope" "$guard" 0 "phase4/run-$tag.jsonl"
        expect="--expect screening=$scr --expect verdict_filter=$vf --expect reverify=$rv --expect output_guard=$guard"
        # With the output guard off, what the poison says cannot change whether
        # it is served, so the script poison would repeat the text-poison run.
        kinds="secret script"
        [ "$guard" = "off" ] && kinds="secret"
        for kind in $kinds; do
            for label in clean attack; do
                in_attacks python attacks/run_bypass.py --threshold 0.85 --tag "$tag" --order "$order" \
                    --out "$OUT" --poison-label "$label" --poison-kind "$kind" $expect $LIMIT_ARG
            done
        done
        in_attacks python attacks/run_benign.py --threshold 0.85 --tag "$tag" --order "$order" \
            --out "$OUT" $expect $LIMIT_ARG
    done
}

warm_cache() {  # ask each honest control once, so repeats in the trace can hit
    # -i: the script comes in on stdin.
    docker run --rm -i --network container:sentrygate-gateway -v "$PWD":/src -w /src sentrygate-attacks python - <<'PY'
import json, urllib.request
base = "http://127.0.0.1:8000"
urllib.request.urlopen(urllib.request.Request(base + "/v1/cache/clear", data=b"{}", method="POST"))
for line in open("data/week4/controls.jsonl"):
    text = json.loads(line)["text"]
    body = json.dumps({"model": "gpt-4o-mini", "messages": [{"role": "user", "content": text}]}).encode()
    req = urllib.request.Request(base + "/v1/chat/completions", data=body, method="POST",
                                 headers={"content-type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=60).read()
    except Exception:
        pass  # a false alarm blocks one control; the rest still warm the cache
PY
}

run_load() {
    echo "Load: $LOAD_SECONDS s per step, users: $LOAD_USERS."
    mkdir -p "$OUT/locust"
    rm -f "$OUT"/locust/* "$OUT"/load-*.jsonl "$OUT"/load-*.warm
    # tag  verdict_filter  reverify  scope  guard
    for arm in "open     off off risky off" \
               "defended on  on  all   block"; do
        set -- $arm
        tag=$1; vf=$2; rv=$3; scope=$4; guard=$5
        for users in $LOAD_USERS; do
            echo "  $tag, $users users"
            start_gateway cache_first on "$vf" "$rv" "$scope" "$guard" 1900 "phase4/load-$tag-u$users.jsonl"
            warm_cache
            # Only the timed run counts. The report skips the warm-up lines,
            # whose count is saved here (the gateway holds the log open).
            wc -l < "data/phase4/load-$tag-u$users.jsonl" | tr -d ' ' > "data/phase4/load-$tag-u$users.warm"
            in_attacks locust -f eval/locustfile.py --headless -u "$users" -r "$users" \
                -t "${LOAD_SECONDS}s" --host http://nginx:80 --only-summary \
                --csv "$OUT/locust/$tag-u$users" >/dev/null 2>&1
        done
    done
}

case "$PART" in
    screening) run_screening ;;
    ablation)  run_ablation ;;
    load)      run_load ;;
    all)       run_screening; run_ablation; run_load ;;
    *) echo "unknown part: $PART" >&2; exit 2 ;;
esac

echo "Done. Building Phase 4 figures."
in_attacks python -m eval.phase4_report
