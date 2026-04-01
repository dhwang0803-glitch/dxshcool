# 데이터 파이프라인 현황 & API 서버 구동 준비 상태

> 최종 업데이트: 2026-03-23
> 목적: 다른 PC/담당자가 이어서 작업할 때 현재 상태를 빠르게 파악하기 위한 문서

---

## 0. 홈 배너 구조 (확정)

```
[로그인 유저 홈 화면]
┌─────────────────────────────────────────────┐
│ 히어로 배너 (top 5, 비개인화)                  │ ← serving.popular_recommendation score 내림차순
├─────────────────────────────────────────────┤
│ 공통 인기 추천 (CT_CL 4종 × 20건 = 80건)       │ ← serving.popular_recommendation (/home/sections)
├─────────────────────────────────────────────┤
│ 개인 선호 태그 선반 (top 5 태그 × 10 VOD)      │ ← serving.tag_recommendation
├─────────────────────────────────────────────┤
│ 개인화 추천 (top 10, 로그인 유저만)            │ ← serving.hybrid_recommendation (rank 1~10)
└─────────────────────────────────────────────┘

[비로그인]
  → 히어로 배너(popular top 5) + 공통 인기(80건)만 노출
```

> 히어로 배너 = 공통 인기 점수 기반 top 5 (누가 봐도 잘 팔릴 콘텐츠, 비개인화).
> `serving.personalized_banner` 별도 테이블 불필요.

---

## 1. DB 테이블 실측 현황 (2026-03-23 기준)

### serving 스키마 (API 서버가 직접 소비)

| 테이블 | 건수 | 상태 | 생산 브랜치 |
|--------|-----:|------|------------|
| `serving.vod_recommendation` | 7,248,640 | ✅ 정상 | CF_Engine + Vector_Search |
| `serving.popular_recommendation` | 80 | ✅ 정상 (CT_CL 4종 × 20건, 의도된 설계) | Normal_Recommendation |
| `serving.hybrid_recommendation` | 2,427,020 | ✅ 정상 (Hybrid Phase 3 완료 2026-03-23) | Hybrid_Layer |
| `serving.tag_recommendation` | 7,531,491 | ✅ 정상 (Hybrid Phase 4 완료 2026-03-23) | Hybrid_Layer |

> `serving.vod_recommendation` 타입별: COLLABORATIVE 4,854,040 / CONTENT_BASED 2,394,600

### public 스키마 (기반 데이터)

| 테이블 | 건수 | 상태 |
|--------|-----:|------|
| `public.vod` | 169,581 | ✅ 정상 |
| `public.user` | 242,702 | ✅ 정상 |
| `public.vod_tag` | 1,331,164 | ✅ 정상 (Hybrid Phase 1 완료) |
| `public.user_preference` | 3,286,989 | ✅ 정상 (Hybrid Phase 2 완료 2026-03-23) |
| `public.watch_history` | 3,992,530 | ✅ 정상 |
| `public.episode_progress` | 2,369,154 | ✅ 정상 |
| `public.purchase_history` | 333,565 | ✅ 정상 |
| `public.point_history` | 0 | ⚠️ 시뮬레이션 데이터 없음 |
| `public.wishlist` | 0 | ⚠️ 시뮬레이션 데이터 없음 |
| `public.watch_reservation` | 0 | ⚠️ 시뮬레이션 데이터 없음 |

---

## 2. API 엔드포인트별 동작 가능 여부

| 엔드포인트 | 현재 상태 | 이유 |
|-----------|-----------|------|
| `GET /vod/{asset_id}` | ✅ **정상 동작** | public.vod 완비 |
| `GET /vod/search?q=` | ✅ **정상 동작** | public.vod 완비 |
| `POST /auth/token` | ✅ **정상 동작** | DB 불필요 |
| `GET /series/{id}/episodes` | ✅ **정상 동작** | public.vod 완비 |
| `GET /series/{id}/purchase-check` | ✅ **정상 동작** | purchase_history 완비 |
| `GET /user/me/history` | ✅ **정상 동작** | episode_progress 완비 |
| `GET /user/me/purchases` | ✅ **정상 동작** | purchase_history 완비 |
| `GET /similar/{asset_id}` | ✅ **정상 동작** | CONTENT_BASED 2.4M건 존재 |
| `GET /home/banner` (비로그인) | ✅ **동작** | popular_recommendation 80건 (CT_CL 4종×20, 의도된 설계) |
| `GET /home/sections` | ✅ **동작** | popular_recommendation 80건 정상 서빙 |
| `GET /recommend/{user_id}` | ✅ **정상 동작** | hybrid_recommendation 2.4M건 완비 |
| `GET /home/banner` (로그인, 히어로) | ✅ **정상 동작** | hybrid_recommendation rank 1~5 |
| `GET /home/banner` (로그인, 하단) | ✅ **정상 동작** | hybrid_recommendation rank 1~10 |
| `GET /home/sections/{user_id}` (태그) | ✅ **정상 동작** | tag_recommendation 7.5M건 완비 |

---

## 3. 남은 작업 순서 (우선순위 순)

### ✅ 완료 — Hybrid_Layer 파이프라인

2026-03-23 기준 Phase 1~4 모두 완료.

| Phase | 내용 | 산출물 |
|-------|------|--------|
| Phase 1 | vod → vod_tag | 1,331,164건 |
| Phase 2 | watch_history × vod_tag → user_preference | 3,286,989건 |
| Phase 3 | CF+Vector 리랭킹 → hybrid_recommendation | 2,427,020건 |
| Phase 4 | 선호 태그 × VOD → tag_recommendation | 7,531,491건 |

재실행이 필요한 경우 (신규 유저 추가 / VOD 업데이트 시):

```bash
conda activate myenv
python Hybrid_Layer/scripts/run_pipeline.py   # Phase 1~4 순차 실행 (TRUNCATE 후 재적재)
```

---

### 🟢 선택 — 시뮬레이션 데이터 적재

`point_history`, `wishlist`, `watch_reservation`이 모두 0건.
데모/테스트 시 실제처럼 보이게 하려면 더미 데이터 삽입 필요.

---

## 4. 완료된 파이프라인 (재실행 불필요)

| 브랜치 | 완료 작업 | 산출물 |
|--------|---------|--------|
| `Database_Design` | 스키마 DDL, 마이그레이션 | 전체 테이블 구조 |
| `RAG` | 메타데이터 결측치 자동수집 | director 92.5%, cast_lead 72.0% 등 |
| `Poster_Collection` | Naver 포스터 수집 → DB 적재 | vod.poster_url 33,662건 업데이트 |
| `CF_Engine` | ALS 협업 필터링 학습 + 적재 | serving.vod_recommendation COLLABORATIVE 4,854,040건 |
| `Vector_Search` | 콘텐츠 기반 유사도 적재 | serving.vod_recommendation CONTENT_BASED 2,394,600건 |
| `Hybrid_Layer` Phase 1~4 | vod_tag → user_preference → hybrid_recommendation → tag_recommendation | 1.3M / 3.3M / 2.4M / 7.5M건 |

---

## 5. 환경 정보

| 항목 | 값 |
|------|-----|
| Python 환경 | `conda activate myenv` (Python 3.12) |
| DB | PostgreSQL on VPC |
| 접속 정보 | 프로젝트 루트 `.env` 파일 |
| 실행 위치 | 항상 **프로젝트 루트**에서 실행 (`python Hybrid_Layer/scripts/...`) |
| psql 경로 | `C:/Program Files/PostgreSQL/18/bin/psql.exe` (PATH 미등록 — Python psycopg2 권장) |

### DB 접속 확인

```bash
conda activate myenv
python -c "
from dotenv import load_dotenv; load_dotenv(); import psycopg2, os
conn = psycopg2.connect(host=os.getenv('DB_HOST'), port=os.getenv('DB_PORT'),
    dbname=os.getenv('DB_NAME'), user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'))
print('DB 연결 성공')
conn.close()
"
```

---

## 6. 현재 브랜치별 작업 상태

| 브랜치 | 상태 | 다음 할 일 |
|--------|------|-----------|
| `main` | ✅ 최신 | — |
| `Database_Design` | ✅ 완료 | — |
| `RAG` | ✅ 완료 | cast_guest 파이프라인 잔여 (선택) |
| `VOD_Embedding` | 🔄 진행 중 | YouTube ID 백필 중 (IP 차단 이슈로 일부 실패) |
| `CF_Engine` | ✅ 완료 | — |
| `Vector_Search` | ✅ 완료 (CONTENT_BASED) | VISUAL_SIMILARITY 추가 가능 |
| `Normal_Recommendation` | ✅ 완료 | popular_recommendation 80건 = CT_CL 4종×20건 의도된 설계 |
| `Hybrid_Layer` | ✅ 완료 | Phase 1~4 모두 완료 (2026-03-23) |
| `API_Server` | ✅ 구현 완료 | 데이터 채워지면 바로 서빙 가능 |
| `Frontend` | — | API_Server 구동 후 연동 |
