# 접근법 비교 실험 계획 — 검색엔진 vs 진짜 RAG

**목적**: 두 접근법을 동일 샘플에 실행하고 지표를 비교해 최종 방향 결정
**선행 조건**: PLAN_01 완료 (search_functions.py, validation.py 존재)
**샘플**: VOD DB에서 director 결측치 100건 층화추출 (ct_cl 기준)

---

## 접근법 A — 현재 방식 (검색엔진 + Regex)

**구조**
```
asset_nm → Wikipedia API → Regex 추출 → IMDB API → Ollama 직접 질의
```

**이미 구현됨**: `RAG/src/search_functions.py`

**추가 작업 없음** — 100건 실행 후 결과만 수집

---

## 접근법 B — 진짜 RAG (Embed → Retrieve → Generate)

**구조**
```
asset_nm
  → Wikipedia 문서 fetch
  → KR-SBERT로 청크 임베딩 → ChromaDB 저장   ← Retrieve
  → 유사도 상위 K 청크를 LLM 프롬프트 context에 삽입  ← Augment
  → exaone3.5가 context 기반으로 감독명 생성  ← Generate
```

**구현 필요 파일**: `RAG/src/rag_engine.py`

```python
class RAGEngine:
    def __init__(self):
        # sentence-transformers: snunlp/KR-SBERT-V40K-klueNLI-augmented
        # chromadb: RAG/config/chroma_db/
        ...

    def index_document(self, asset_nm: str, text: str) -> None:
        """Wikipedia 문서를 청크로 분할 후 ChromaDB에 임베딩 적재"""
        # chunk_size=200자, overlap=50자
        ...

    def retrieve(self, query: str, k: int = 3) -> list[str]:
        """쿼리 임베딩 → 유사도 상위 k 청크 반환"""
        ...

    def generate(self, asset_nm: str, context_chunks: list[str], field: str) -> str | None:
        """context를 붙인 프롬프트로 exaone3.5 호출"""
        prompt = f"""다음 정보를 참고해서 영화 "{asset_nm}"의 {field}만 한 줄로 답해줘.
모르면 "없음"이라고 답해.

[참고 정보]
{chr(10).join(context_chunks)}

{field}:"""
        ...

    def search_with_rag(self, asset_nm: str, field: str) -> str | None:
        """전체 RAG 파이프라인: fetch → index → retrieve → generate"""
        ...
```

---

## 비교 실험 설계

### 공통 샘플
```python
# DB에서 director 결측 VOD 100건 층화추출
# RAG/data/comparison_sample.csv 저장
SELECT full_asset_id, asset_nm, ct_cl
FROM vod
WHERE director IS NULL AND asset_nm IS NOT NULL
ORDER BY RANDOM()
LIMIT 100;
```

### 실행 순서
1. 접근법 A로 100건 실행 → `RAG/reports/result_A.json`
2. 접근법 B로 100건 실행 → `RAG/reports/result_B.json`
3. 두 결과를 수동 샘플링 20건 검증

### 측정 지표

| 지표 | 측정 방법 |
|------|----------|
| **검색 성공률** | non-NULL 반환 건수 / 100 |
| **정확도** | 수동 검증 20건 중 정답 비율 |
| **평균 처리 시간** | 건당 wall-clock time |
| **신뢰도 평균** | confidence_score 평균 |
| **API 의존도** | IMDB API 없이도 작동 여부 |

### 예상 트레이드오프

| | 접근법 A | 접근법 B |
|--|---------|---------|
| 성공률 | 중간 (Regex 한계) | 높음 (LLM 유연성) |
| 정확도 | 중간 | 높음 (context 기반) |
| 처리 시간 | 빠름 (~3초/건) | 느림 (~15초/건, 임베딩 포함) |
| 구현 복잡도 | 낮음 (완료) | 높음 (chromadb 연동) |
| 오프라인 가능 | ❌ (Wikipedia 필요) | ❌ (Wikipedia fetch 필요) |
| IMDB API 필요 | 선택 | 불필요 |

---

## 구현 태스크 (다음 세션)

### Step 1: 샘플 추출 스크립트
- `RAG/src/extract_sample.py` — DB에서 100건 추출 → CSV 저장

### Step 2: 접근법 A 배치 실행
- `RAG/src/run_approach_a.py` — search_functions.py 활용, 결과 JSON 저장

### Step 3: 접근법 B 구현 및 실행
- `RAG/src/rag_engine.py` — RAGEngine 클래스 구현
- `RAG/src/run_approach_b.py` — 100건 RAG 실행

### Step 4: 비교 리포트 생성
- `RAG/src/compare_results.py` — 두 JSON 비교, 지표 출력
- `RAG/reports/approach_comparison.md` — 최종 방향 결정 근거

---

## 방향 결정 기준

```
정확도 차이 < 5%  AND  처리시간 B > 10초/건  →  접근법 A 채택 (단순함 우선)
정확도 차이 ≥ 5%  OR   처리시간 B ≤ 10초/건  →  접근법 B 채택 (정확도 우선)
```

**다음 세션 시작 시**: `/rag-init` 후 이 파일부터 읽고 Step 1부터 진행
