# Refactor Agent — Object_Detection

## 역할
모든 테스트가 PASS된 이후에만 실행된다.
테스트를 통과한 상태를 유지하면서 코드 품질을 개선한다 (TDD Refactor 단계).

---

## 핵심 원칙

1. **테스트 통과 상태 유지**: 리팩토링 후 반드시 전체 테스트 재실행하여 PASS 확인
2. **기능 변경 금지**: 동작 결과가 달라지는 변경은 하지 않는다
3. **범위 제한**: 해당 Phase의 `src/`, `scripts/` 파일만 수정한다
4. **작은 단위로 개선**: 한 번에 하나씩 개선하고 테스트 확인 후 다음으로 넘어간다

---

## 개선 검토 항목

### Python 코드 품질
- [ ] 중복 로직 → 공통 함수로 통합 (예: 프레임 샘플링 로직)
- [ ] 에러 처리 누락 (영상 열기 실패, 모델 로드 실패)
- [ ] 하드코딩된 값 → config 파일 참조 또는 인자로 위임
- [ ] 로깅 메시지 명확성 (어떤 VOD에서 어떤 프레임이 실패했는지)

### 성능 관점
- [ ] 프레임 배치 크기 최적화 (GPU 환경에서 batch_size > 1 활용)
- [ ] 불필요한 프레임 복사 제거 (numpy in-place 연산)
- [ ] parquet append 빈도 최적화 (batch_save_interval 조정)
- [ ] 메모리 누수 확인 (VideoCapture 명시적 release)

### 데이터 품질
- [ ] bbox 좌표 유효성 검증 (음수, 프레임 크기 초과 제거)
- [ ] 동일 프레임 내 중복 label 처리 (NMS 후처리 확인)
- [ ] parquet 타입 일관성 (vod_id: str, confidence: float64 등)

---

## 리팩토링 범위 제한 — 제외 대상

- 테스트 파일 (`tests/`)
- PLAN 문서 (`docs/plans/`)
- 설정 파일 (`config/`)
- 에이전트 문서 (`agents/`)

---

## 리팩토링 완료 후 확인

```bash
# 전체 테스트 재실행
conda run -n myenv python -m pytest Object_Detection/tests/ -v 2>&1

# 이전 결과와 PASS/FAIL 건수 동일한지 비교
```

## Reporter Agent에 전달할 개선 내용 형식

```
[리팩토링 항목]
- 파일: [파일명]
- 변경 전: [기존 코드/구조 요약]
- 변경 후: [개선된 코드/구조 요약]
- 개선 이유: [왜 개선했는지]
```
