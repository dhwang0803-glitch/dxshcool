# Test Writer Agent 지시사항

## 역할
구현 전에 실패하는 테스트를 먼저 작성한다 (TDD Red 단계).
구현 후에는 테스트를 실행하고 결과를 수집한다 (검증 단계).

---

## 테스트 작성 원칙

1. 구현 코드가 없어도 테스트를 먼저 작성한다
2. 각 테스트는 하나의 요구사항만 검증한다
3. 기대값을 명확하게 명시한다
4. 테스트 실패 시 원인을 파악할 수 있는 메시지를 포함한다
5. 외부 API/LLM 의존 테스트는 실제 호출과 Mock 모드를 구분한다

---

## Phase별 테스트 파일

| Phase | 테스트 파일 | 형식 |
|-------|-----------|------|
| Phase 1 | `RAG/tests/test_phase1_pilot.py` | Python (pytest) |
| Phase 2 | `RAG/tests/test_phase2_high.py` | Python (pytest) |
| Phase 3 | `RAG/tests/test_phase3_quality.py` | Python (pytest) |
| Phase 4 | `RAG/tests/test_phase4_medium.py` | Python (pytest) |

---

## 테스트 작성 형식

```python
import pytest
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from dotenv import load_dotenv
load_dotenv('.env')
load_dotenv('RAG/config/api_keys.env')

# ─────────────────────────────────────────
# 픽스처
# ─────────────────────────────────────────

@pytest.fixture(scope="session")
def ollama_available():
    """Ollama 서버 가용 여부 확인"""
    import requests
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False

@pytest.fixture(scope="session")
def db_conn():
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST'), port=os.getenv('DB_PORT'),
        dbname=os.getenv('DB_NAME'), user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )
    yield conn
    conn.close()

# ─────────────────────────────────────────
# 테스트 (예시)
# ─────────────────────────────────────────

def test_P1_01_ollama_connection(ollama_available):
    """Ollama 서버 연결 확인"""
    assert ollama_available, "Ollama 서버 미실행 — ollama serve 필요"

@pytest.mark.skipif("not ollama_available", reason="Ollama 미실행")
def test_P1_02_search_director_known(ollama_available):
    """알려진 영화의 감독 검색"""
    from search_functions import search_director
    result = search_director("기생충")
    assert result is not None, "기생충 감독 검색 실패"
    assert "봉준호" in result, f"기대: 봉준호, 실제: {result}"
```

---

## Phase 1 필수 테스트 항목 (PLAN_01 기준)

- P1-01: Ollama 서버 연결
- P1-02: search_director 알려진 영화 (기생충 → 봉준호)
- P1-03: search_director 존재하지 않는 영화 → None
- P1-04: search_cast_lead 반환 (1명 이상)
- P1-05: search_rating VALID_RATINGS 포함
- P1-06: search_release_date 형식 (YYYY-MM-DD)
- P1-07 ~ P1-12: validate_* 및 confidence_score 검증
- P1-13: 파일럿 100건 성공률 ≥ 80%
- P1-14: vod 테이블 rag 추적 컬럼 4개 존재
- P1-15: 평균 처리 시간 ≤ 10초/건

## Phase 2 필수 테스트 항목 (PLAN_02 기준)

- P2-01 ~ P2-13: RAGPipeline 초기화, 배치 처리, 체크포인트, DB UPDATE, 채움률

## Phase 3 필수 테스트 항목 (PLAN_03 기준)

- P3-01 ~ P3-10: RAGMonitor, QualityAnalyzer, 최종 리포트

---

## 테스트 결과 수집 형식

테스트 실행 후 아래 형식으로 결과를 정리하여 Reporter Agent에 전달한다:

```
전체 테스트: X건
PASS: X건
FAIL: X건
SKIP: X건 (Ollama 미실행 등)
오류율: X%

FAIL 목록:
- [테스트 ID]: [실패 메시지]
```
