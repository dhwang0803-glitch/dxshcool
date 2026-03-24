# User_Embedding 파이프라인 실행 결과 리포트

**실행일**: 2026-03-15
**브랜치**: `User_Embedding`
**담당**: 데이터 인프라 팀

---

## 실행 환경

| 항목 | 값 |
|------|----|
| Python 환경 | `myenv` (Python 3.12) |
| 실행 스크립트 | `scripts/run_embed.py` |
| DB | PostgreSQL + pgvector (VPC) |

---

## 입력 데이터 현황

| 테이블 | 건수 | 비고 |
|--------|------|------|
| `watch_history` | 3,992,530건 | 시청 이력 전체 |
| `watch_history` (unique users) | 242,702명 | 임베딩 대상 |
| `vod_embedding` | 146,390건 | CLIP ViT-B/32, 512차원 |
| `vod_meta_embedding` | 166,159건 | paraphrase-multilingual-MiniLM-L12-v2, 384차원 |

---

## 실행 결과

| 항목 | 값 |
|------|----|
| 처리 대상 유저 | 242,702명 |
| 임베딩 생성·적재 | **225,259명** |
| 스킵 (결합 임베딩 없는 VOD만 시청) | 17,443명 (7.2%) |
| 적재 성공률 | **92.8%** |

### user_embedding 테이블 최종 현황

| 지표 | 값 |
|------|----|
| 총 적재 건수 | 225,259건 |
| vod_count 최솟값 | 1 |
| vod_count 최댓값 | 6,520 |
| vod_count 평균 | 15.1 |
| vector_magnitude 최솟값 | 1.0000 |
| vector_magnitude 최댓값 | 1.0000 |
| vector_magnitude 평균 | 1.0000 |

> **L2 정규화 검증 통과** — 전체 벡터 magnitude = 1.0 (cosine similarity 연산 준비 완료)

---

## 생성 방식

```
watch_history (user_id_fk, vod_id_fk, completion_rate)
    ↓ JOIN
vod_embedding (512차원) + vod_meta_embedding (384차원)
    ↓ concat
결합 임베딩 (896차원, 런타임 계산)
    ↓ weighted_mean(weights=completion_rate)
유저 벡터 (896차원)
    ↓ L2 정규화
user_embedding 테이블 upsert (ON CONFLICT user_id_fk DO UPDATE)
```

- **차원**: 896 (CLIP 512 + META 384)
- **가중치**: `completion_rate` (0~1)
- **멱등성**: 동일 `user_id_fk` 재실행 시 덮어쓰기

---

## 스킵 원인 분석

스킵 17,443명(7.2%)은 시청한 모든 VOD에 `vod_embedding` 또는 `vod_meta_embedding`이 없는 경우.
주요 원인:
- 트레일러 크롤링 미완료 VOD (CLIP 임베딩 없음)
- 메타데이터 미확보 VOD (META 임베딩 없음)

`vod_embedding` 커버리지가 87.5% (146,390/166,159)이므로 향후 크롤링 보완 시 스킵 유저 추가 처리 가능.

---

## 다운스트림 연계

| 브랜치 | 용도 |
|--------|------|
| `Vector_Search` | `user_embedding` ↔ `vod_embedding` cosine similarity 검색 |
| `CF_Engine` | ALS 행렬 분해 (user-item interaction 기반) |

---

## 파일럿 결과 (사전 검증, 100명)

| 항목 | 값 |
|------|----|
| 파이럿 대상 | 100명 |
| 성공 | 94명 |
| 스킵 | 6명 |
| 결과 | 전체 실행과 동일한 패턴 확인 후 full run 진행 |
