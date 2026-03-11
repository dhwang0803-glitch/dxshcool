# PLAN_01: 메타데이터 기반 콘텐츠 유사도

**파일**: `src/content_based.py`, `scripts/build_index.py`
**입력**: vod 테이블 (장르, 감독, 배우, 줄거리)
**출력**: SBERT 코사인 유사도 스코어

---

## 목표

vod 메타데이터를 SBERT로 임베딩하여 텍스트 기반 유사 콘텐츠를 검색한다.

---

## 모델

- **SBERT**: `jhgan/ko-sroberta-multitask` (한국어 특화)
- 입력 텍스트: `장르 + 감독 + 배우 + 줄거리` 결합 문자열
- 출력: 768차원 float32 벡터

---

## 구현 (`src/content_based.py`)

```python
from sentence_transformers import SentenceTransformer
import numpy as np

MODEL_NAME = "jhgan/ko-sroberta-multitask"

def build_meta_text(vod: dict) -> str:
    """메타데이터 → 단일 텍스트 결합"""
    parts = [
        vod.get("genre", ""),
        vod.get("director", ""),
        vod.get("cast_lead", ""),
        vod.get("smry", ""),
    ]
    return " ".join(p for p in parts if p)

def encode_metadata(vod_list: list, model: SentenceTransformer) -> np.ndarray:
    """VOD 목록 → SBERT 임베딩 행렬 (N x 768)"""
    texts = [build_meta_text(v) for v in vod_list]
    return model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)

def cosine_similarity(query_vec: np.ndarray, index_vecs: np.ndarray) -> np.ndarray:
    """정규화된 벡터 간 코사인 유사도 (내적 = 코사인)"""
    return index_vecs @ query_vec
```

---

## 인덱스 빌드 (`scripts/build_index.py`)

1. vod 테이블 전체 조회 (메타데이터 컬럼)
2. SBERT 임베딩 → `data/content_index.pkl` 저장
3. vod_id 매핑 테이블 함께 저장

```bash
python scripts/build_index.py
```

---

## 검색 흐름

```
쿼리 vod_id → 해당 메타텍스트 → SBERT 인코딩 → 인덱스와 코사인 유사도 → TOP-N 반환
```

---

## 주의사항

- `smry`(줄거리) NULL 비율 약 0% (DB 현황 기준 거의 채워짐)
- `cast_lead` NULL 28% → NULL 시 빈 문자열로 처리
- `director` NULL 7.5% → NULL 시 빈 문자열로 처리
- 인덱스는 vod 테이블 갱신 시 재빌드 필요

---

**다음**: PLAN_02_CLIP_BASED.md
