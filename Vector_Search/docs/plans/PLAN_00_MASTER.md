# PLAN_00: Vector Search 마스터 플랜

**브랜치**: Vector_Search
**목표**: 메타데이터 기반 + CLIP 영상 기반 유사도 검색 엔진 2종 구현 및 앙상블

---

## 전체 구조

```
[PLAN_01] vod_meta_embedding 테이블 (384차원) → pgvector <=> 코사인 검색 → content_score
                ↓
[PLAN_02] vod_embedding 테이블 (512차원) → pgvector <=> 코사인 검색 → clip_score
                ↓
[PLAN_03] 두 스코어 앙상블 → 최종 유사 콘텐츠 순위
                ↓
[PLAN_04] 결과 DB 적재 → serving.vod_recommendation → API_Server 연동
```

---

## 단계별 요약

| 단계 | 파일 | 입력 | 출력 |
|------|------|------|------|
| PLAN_01 | `src/content_based.py` | vod_meta_embedding (384차원) | content_score |
| PLAN_02 | `src/clip_based.py` | vod_embedding (512차원) | clip_score |
| PLAN_03 | `src/ensemble.py` + `scripts/search.py` | PLAN_01·02 스코어 | 최종 유사 콘텐츠 TOP-N |
| PLAN_04 | `scripts/export_to_db.py` | TOP-N 결과 | serving.vod_recommendation 적재 |

---

## 업스트림 의존성

| 브랜치 | 제공 데이터 |
|--------|------------|
| `VOD_Embedding` | vod_meta_embedding 테이블 (384차원, paraphrase-multilingual-MiniLM-L12-v2) |
| `VOD_Embedding` | vod_embedding 테이블 (CLIP 512차원) |

---

## 진행 체크리스트

- [ ] PLAN_01: vod_meta_embedding pgvector 검색 구현
- [ ] PLAN_02: pgvector CLIP 기반 유사도 구현
- [ ] PLAN_03: 앙상블 로직 + 검색 스크립트
- [ ] PLAN_04: serving.vod_recommendation 적재
