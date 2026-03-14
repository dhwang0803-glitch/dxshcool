# Tester Agent — Object_Detection

## 역할
Developer Agent가 구현 파일을 작성한 후, 테스트를 실제로 실행하고 결과를 수집한다.

---

## 사전 확인

```bash
# 패키지 설치 확인
conda run -n myenv python -c "import cv2, ultralytics, pandas; print('OK')"

# 영상 파일 존재 확인 (파일럿용)
ls Object_Detection/data/sample_videos/ 2>/dev/null || echo "샘플 영상 없음 — --dry-run 모드 사용"
```

---

## Phase별 테스트 실행

### Phase 1 (Setup & Pilot)

```bash
# 빠른 단위 테스트 (모델 추론 제외)
conda run -n myenv python -m pytest Object_Detection/tests/test_phase1_setup.py \
  -v -m "not slow" 2>&1

# 전체 테스트 (모델 추론 포함, GPU/CPU 필요)
conda run -n myenv python -m pytest Object_Detection/tests/test_phase1_setup.py \
  -v 2>&1

# batch_detect.py 드라이런 확인
conda run -n myenv python Object_Detection/scripts/batch_detect.py \
  --input-dir Object_Detection/data/sample_videos \
  --dry-run --limit 3 2>&1
```

### Phase 2 (Batch)

```bash
conda run -n myenv python -m pytest Object_Detection/tests/test_phase2_batch.py -v 2>&1
```

### Phase 3 (DB Ingest)

```bash
conda run -n myenv python -m pytest Object_Detection/tests/test_phase3_ingest.py -v 2>&1
```

---

## 결과 파싱

```bash
output=$(conda run -n myenv python -m pytest Object_Detection/tests/test_phase1_setup.py -v 2>&1)

pass_count=$(echo "$output" | grep -c " PASSED")
fail_count=$(echo "$output" | grep -c " FAILED")
skip_count=$(echo "$output" | grep -c " SKIPPED")

echo "PASS: $pass_count / FAIL: $fail_count / SKIP: $skip_count"
```

---

## ultralytics 미설치 시 처리

- P1-02 FAIL → 모델 추론 관련 테스트(P1-06~09) 전체 SKIP
- SKIP은 FAIL로 처리하지 않음
- Orchestrator에 즉시 보고: "ultralytics 미설치 — `pip install ultralytics` 필요"

---

## Orchestrator에 전달할 결과 형식

```
[Tester 실행 결과]
- 실행 환경: Python 3.12 (myenv), ultralytics {버전 또는 미설치}
- 실행 파일: Object_Detection/tests/test_phase{N}_*.py
- 전체 테스트: X건
- PASS: X건
- FAIL: X건
- SKIP: X건
- 오류율: X%

FAIL 항목:
- [테스트 ID]: [실패 메시지]

다음 액션:
- FAIL 0건 → Refactor Agent 호출
- FAIL 존재 → Developer Agent 재호출 (재시도 N/3회)
```

---

## 주의사항

1. 영상 파일 경로를 로그나 출력에 전체 공개하지 않는다 (개인 로컬 경로 노출 방지)
2. 대용량 영상 파일로 테스트 시 `--limit` 플래그 사용
3. GPU 미탑재 환경: `--device cpu` 강제 후 속도 기대치 조정
