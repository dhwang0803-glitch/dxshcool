#!/usr/bin/env bash
# Ollama 상태 모니터링 + fill_seed_sentences 자동 재시작
# Usage: bash gen_rec_sentence/scripts/monitor_batch.sh

OLLAMA_EXE="C:/Users/daewo/AppData/Local/Programs/Ollama/ollama.exe"
PYTHON="/c/Users/daewo/anaconda3/envs/myenv/python.exe"
LOG="/tmp/fill_seed_new.log"
MONITOR_LOG="/tmp/monitor_batch.log"
TOTAL=100

# 항상 프로젝트 루트에서 실행
cd "/c/Users/daewo/OneDrive/문서/GitHub/dxshcool" || { echo "프로젝트 루트 이동 실패"; exit 1; }

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$MONITOR_LOG"
}

get_done_count() {
    "$PYTHON" -c "
import json, sys
sys.stdout.reconfigure(encoding='utf-8')
count = 0
with open('gen_rec_sentence/data/seed_examples.jsonl', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        if d.get('output', {}).get('rec_sentence', ''):
            count += 1
print(count)
" 2>/dev/null
}

start_fill() {
    local start=$1
    local size=$((TOTAL - start))
    if [ "$size" -le 0 ]; then
        log "✅ 모든 항목 완료. 모니터링 종료."
        exit 0
    fi
    log "▶ fill_seed_sentences 시작: --batch-start $start --batch-size $size"
    "$PYTHON" gen_rec_sentence/scripts/fill_seed_sentences.py \
        --batch-start "$start" --batch-size "$size" --no-visual >> "$LOG" 2>&1 &
    echo $!
}

check_ollama() {
    curl -s http://localhost:11434/api/tags > /dev/null 2>&1
    return $?
}

restart_ollama() {
    log "⚠ Ollama 다운 감지 → CPU 모드로 재시작"
    taskkill //F //IM ollama.exe 2>/dev/null || true
    sleep 3
    # CUDA 완전 비활성화 (-1: 장치 없음으로 인식)
    export CUDA_VISIBLE_DEVICES="-1"
    export OLLAMA_NUM_GPU=0
    "$OLLAMA_EXE" serve &>/dev/null &
    sleep 8
    if check_ollama; then
        log "✅ Ollama 재시작 성공 (CPU 전용)"
        return 0
    else
        log "❌ Ollama 재시작 실패 — 10초 후 재시도"
        sleep 10
        return 1
    fi
}

log "=== 모니터 시작 (총 ${TOTAL}건) ==="

# 초기 Ollama 확인
if ! check_ollama; then
    restart_ollama
fi

# 현재 완료된 수 확인 후 시작
DONE=$(get_done_count)
log "현재 완료: ${DONE}/${TOTAL}"
FILL_PID=$(start_fill "$DONE")
log "fill_seed PID: $FILL_PID"

# 모니터링 루프 (30초마다 체크)
while true; do
    sleep 30

    # fill_seed 프로세스 살아있는지 확인
    if kill -0 "$FILL_PID" 2>/dev/null; then
        # 실행 중 — Ollama만 체크
        if ! check_ollama; then
            log "⚠ Ollama 다운 (fill_seed 실행 중) → 재시작"
            kill "$FILL_PID" 2>/dev/null
            sleep 2
            restart_ollama
            DONE=$(get_done_count)
            log "재개: ${DONE}/${TOTAL}건 완료"
            FILL_PID=$(start_fill "$DONE")
            log "새 fill_seed PID: $FILL_PID"
        fi
    else
        # 프로세스 종료됨
        DONE=$(get_done_count)
        log "fill_seed 종료 감지. 완료: ${DONE}/${TOTAL}"

        if [ "$DONE" -ge "$TOTAL" ]; then
            log "✅ 전체 완료!"
            exit 0
        fi

        # 미완료 → Ollama 확인 후 재시작
        if ! check_ollama; then
            restart_ollama
        fi
        log "미완료 → 재시작: ${DONE}번부터"
        FILL_PID=$(start_fill "$DONE")
        log "새 fill_seed PID: $FILL_PID"
    fi
done
