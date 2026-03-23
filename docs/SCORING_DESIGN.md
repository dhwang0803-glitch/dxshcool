# 추천 점수 설계 원칙 (SCORING_DESIGN)

> 최종 업데이트: 2026-03-23
> 목적: 두 추천 레이어의 점수 공식 설계 의도와 역할 분리 근거를 기록

---

## 설계 원칙: "역할에 맞는 신호를 쓴다"

이 시스템은 두 종류의 추천 점수를 사용하며, **의도적으로 신호를 분리**한다.

| 레이어 | 테이블 | 목적 | 사용 신호 |
|--------|--------|------|-----------|
| 비개인화 인기 추천 | `serving.popular_recommendation` | 누가 봐도 잘 팔릴 콘텐츠 | TMDB 평점 + 플랫폼 시청량 + 최신성 |
| 개인화 추천 | `serving.hybrid_recommendation` | 이 유저에게 맞는 콘텐츠 | CF/Vector 엔진 점수 + 유저 태그 선호도 |

---

## 1. popularity_score — 비개인화 인기 점수

**생산 브랜치**: `Normal_Recommendation` / `src/popularity.py`

### 공식

시청 이력 유무에 따라 cold/warm 두 단계로 분리하고 선형 블렌딩.

```
blend = clip(watch_count / WARM_THRESHOLD, 0, 1)   # WARM_THRESHOLD = 10

score_cold = 0.65 × vote_score + 0.35 × freshness
score_warm = 0.45 × watch_heat + 0.25 × quality + 0.15 × vote_score + 0.15 × freshness

popularity_score = (1 - blend) × score_cold + blend × score_warm
```

### 컴포넌트

| 컴포넌트 | 신호 출처 | 설명 |
|---------|---------|------|
| `vote_score` | TMDB (글로벌) | 평점 × log 정규화 × credibility 댐핑 (소수 고평가 방지, 상한 50건) |
| `freshness` | `vod.release_date` | 출시 후 1년간 1.0→0.0 선형 감쇄 |
| `watch_heat` | `watch_history` (7일) | 최근 7일 시청 수 / 전체 평균, 상한 5배 정규화 |
| `quality` | `watch_history` | avg(completion_rate) × avg(satisfaction), 최소 5건 이상 시청 시 유효 |

### TMDB 평점을 여기서 쓰는 이유

비개인화 추천은 전체 유저를 대상으로 "객관적으로 좋은 콘텐츠"를 선별하는 것이 목적.
TMDB 글로벌 평점은 다수 의견 기반의 범용 품질 지표로 이 목적에 부합한다.

---

## 2. hybrid_score — 개인화 리랭킹 점수

**생산 브랜치**: `Hybrid_Layer` / `src/reranker.py`

### 공식

```
tag_overlap_score = mean(유저 선호 태그 상위 3개 affinity)

hybrid_score = β × original_score + (1 - β) × tag_overlap_score
              (β 기본값 = 0.6, config에서 조정 가능)
```

### 컴포넌트

| 컴포넌트 | 신호 출처 | 설명 |
|---------|---------|------|
| `original_score` | CF_Engine + Vector_Search | 플랫폼 내 실제 시청 패턴 기반 추천 점수 |
| `tag_overlap_score` | `user_preference` × `vod_tag` | 유저가 즐겨 본 태그(감독/배우/장르 등)와의 매칭 친밀도 평균 |

### TMDB 평점을 여기서 쓰지 않는 이유

> **TMDB 평점은 글로벌 다수 의견이고, 개인화 추천의 목적은 "이 유저의 취향"이다. 둘은 방향이 다르다.**

구체적 문제:
1. 국내 IPTV 이용자 취향 ≠ TMDB 글로벌 유저 취향 (드라마/예능 장르 비중 차이 큼)
2. 할리우드 블록버스터는 vote_count가 압도적으로 많아 국내 콘텐츠 대비 유리한 구조
3. CF/Vector 점수가 이미 플랫폼 실 시청 데이터에서 도출되어 훨씬 relevant한 품질 신호를 내포

### 플랫폼 자체 quality 신호(completion_rate)를 넣지 않는 이유

`quality = avg(completion_rate) × avg(satisfaction)` 지표는 개념적으로 좋으나,
Hybrid_Layer가 이를 별도 집계하면 Normal_Recommendation과 중복 연산이 발생하고
두 브랜치 간 DB 중간 산출물 공유 의존성이 생긴다.
CF 점수가 시청량 기반이므로 quality가 간접 반영되어 있다고 판단하여 제외.

---

## 3. 역할 분리 요약

```
[홈 히어로 배너] — "이건 다 좋아할거야"
  serving.popular_recommendation (score DESC top 5)
  → TMDB 평점 + 플랫폼 시청 데이터 종합
  → 누구에게나 동일하게 노출

[개인화 하단 추천] — "당신이 좋아할거야"
  serving.hybrid_recommendation (rank 1~10)
  → CF/Vector 점수 × 유저 태그 선호도
  → 유저마다 다르게 노출
```

TMDB 평점은 비개인화 레이어에, 플랫폼 행동 신호는 개인화 레이어에 집중시키는 것이
이 시스템의 **점수 설계 원칙**이다.

---

## 4. 향후 고도화 여지

현행 설계를 유지하면서 아래를 검토할 수 있다.

| 항목 | 내용 | 담당 |
|------|------|------|
| β 튜닝 | A/B 테스트로 최적 β 탐색 (현행 0.6) | Hybrid_Layer |
| tag_overlap top_k 조정 | 현행 top 3 → 실험적으로 조정 | Hybrid_Layer |
| freshness 추가 검토 | IPTV 재방 수요 특성상 오래된 콘텐츠가 불리할 필요 없어 현행 미적용 | Hybrid_Layer |
| 플랫폼 quality 통합 | 중복 연산 없이 공유 가능한 구조 마련 시 재검토 | Normal_Recommendation + Hybrid_Layer |
