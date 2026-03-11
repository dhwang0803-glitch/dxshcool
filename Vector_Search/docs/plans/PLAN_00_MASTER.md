# PLAN_00: Vector Search 마스터 플랜

**브랜치**: Vector_Search
**목표**: 메타데이터 기반 + CLIP 영상 기반 유사도 검색 엔진 2종 구현 및 앙상블

---

## 전체 구조

```
[PLAN_01] vod 테이블 메타데이터 → SBERT 임베딩 → 코사인 유사도 검색
                ↓
[PLAN_02] vod_embedding 테이블 CLIP 벡터 → pgvector <=> 코사인 검색
                ↓
[PLAN_03] 두 스코어 앙상블 → 최종 유사 콘텐츠 순위
                ↓
[PLAN_04] 결과 DB 적재 → API_Server 연동
```

---

## 단계별 요약

| 단계 | 파일 | 입력 | 출력 |
|------|------|------|------|
| PLAN_01 | `src/content_based.py` + `scripts/build_index.py` | vod 메타데이터 | SBERT 유사도 스코어 |
| PLAN_02 | `src/clip_based.py` | vod_embedding (512차원) | CLIP 유사도 스코어 |
| PLAN_03 | `src/ensemble.py` + `scripts/search.py` | PLAN_01·02 스코어 | 최종 유사 콘텐츠 TOP-N |
| PLAN_04 | `scripts/export_to_db.py` | TOP-N 결과 | DB 적재 |

---

## 업스트림 의존성

| 브랜치 | 제공 데이터 |
|--------|------------|
| `Database_Design` | vod 테이블 (장르, 감독, 배우, 줄거리) |
| `VOD_Embedding` | vod_embedding 테이블 (CLIP 512차원 벡터) |

---

## 진행 체크리스트

- [ ] PLAN_01: SBERT 인덱스 빌드 및 콘텐츠 기반 유사도 구현
- [ ] PLAN_02: pgvector CLIP 기반 유사도 구현
- [ ] PLAN_03: 앙상블 로직 + 검색 스크립트
- [ ] PLAN_04: 결과 DB 적재
