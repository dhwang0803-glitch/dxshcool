# 데이터 파이프라인 현황 & API 서버 구동 준비 상태

> 최종 업데이트: 2026-03-22
> 목적: 다른 PC/담당자가 이어서 작업할 때 현재 상태를 빠르게 파악하기 위한 문서

---

## 1. DB 테이블 실측 현황 (2026-03-22 기준)

### serving 스키마 (API 서버가 직접 소비)

| 테이블 | 건수 | 상태 | 생산 브랜치 |
|--------|-----:|------|------------|
| `serving.vod_recommendation` | 7,248,640 | ✅ 정상 | CF_Engine + Vector_Search |
| `serving.popular_recommendation` | 80 | ⚠️ 부족 | Normal_Recommendation |
| `serving.hybrid_recommendation` | 0 | ❌ 미생성 | Hybrid_Layer Phase 3 |
| `serving.tag_recommendation` | 0 | ❌ 미생성 | Hybrid_Layer Phase 4 |
| `serving.personalized_banner` | — | ❌ 테이블 없음 | Normal_Recommendation |

> `serving.vod_recommendation` 타입별: COLLABORATIVE 4,854,040 / CONTENT_BASED 2,394,600

### public 스키마 (기반 데이터)

| 테이블 | 건수 | 상태 |
|--------|-----:|------|
| `public.vod` | 169,581 | ✅ 정상 |
| `public.user` | 242,702 | ✅ 정상 |
| `public.vod_tag` | 1,331,164 | ✅ 정상 (Hybrid Phase 1 완료) |
| `public.user_preference` | 0 | ⏳ Hybrid Phase 2 실행 중 |
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
| `GET /home/banner` (비로그인) | ⚠️ **빈 응답** | popular_recommendation 80건만 (CT_CL 4종×20건 수준) |
| `GET /home/sections` | ⚠️ **빈 응답** | popular_recommendation 80건만 |
| `GET /recommend/{user_id}` | ⚠️ **popular fallback** | hybrid/tag 미생성 → 인기 추천으로 대체 |
| `GET /home/banner` (로그인) | ⏳ **Phase 3 완료 후** | hybrid_recommendation 0건 |
| `GET /home/sections/{user_id}` | ⚠️ **popular fallback** | popular 80건만 |

---

## 3. 남은 작업 순서 (우선순위 순)

### 🔴 즉시 필요 — Hybrid_Layer 파이프라인 완료

브랜치: `Hybrid_Layer` / 실행 환경: `myenv` / 작업 디렉토리: 프로젝트 루트

```bash
conda activate myenv

# Phase 2: watch_history × vod_tag → user_preference (실행 중 또는 완료 확인)
python Hybrid_Layer/scripts/build_user_preferences.py

# Phase 3: CF+Vector 후보 리랭킹 → hybrid_recommendation 적재
python Hybrid_Layer/scripts/run_hybrid.py

# Phase 4: 선호 태그별 VOD 선반 → tag_recommendation 적재
python Hybrid_Layer/scripts/build_tag_shelves.py
```

완료 기준:
- `public.user_preference`: 수만 건 이상 적재
- `serving.hybrid_recommendation`: 유저 수 × 10건 수준 적재
- `serving.tag_recommendation`: 유저 수 × 5태그 × 10 VOD 수준 적재

---

### 🔴 즉시 필요 — Normal_Recommendation 재실행

브랜치: `Normal_Recommendation`

현재 `serving.popular_recommendation`이 80건(CT_CL 4종×20)에 불과해 홈 화면이 거의 비어 있음.
**홈 화면의 모든 비개인화 섹션이 이 테이블에 의존하므로 반드시 확장 필요.**

- 담당자: Normal_Recommendation 브랜치 담당자에게 전달
- 필요 작업: popular_recommendation 재생성 (더 많은 VOD 포함, CT_CL별 충분한 수량)
- 관련 파일: `Normal_Recommendation/scripts/` 확인

---

### 🟡 필요 — serving.personalized_banner 테이블 생성

현재 테이블 자체가 없음. API 서버 코드는 `try/except`로 예외 처리되어 있어 에러는 안 나지만,
로그인 유저의 홈 배너 1단(개인화 top 5)이 완전히 비어 있음.

- 담당자: Database_Design 브랜치에서 DDL 추가
- 참고: `Database_Design/docs/DEPENDENCY_MAP.md`의 serving.personalized_banner 스키마 확인
- 생성 후 Normal_Recommendation에서 데이터 적재 필요

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
| `Hybrid_Layer` Phase 1 | vod → vod_tag 태그 추출 | public.vod_tag 1,331,164건 |

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
| `Database_Design` | ✅ 완료 | personalized_banner DDL 추가 필요 |
| `RAG` | ✅ 완료 | cast_guest 파이프라인 잔여 (선택) |
| `VOD_Embedding` | 🔄 진행 중 | YouTube ID 백필 중 (IP 차단 이슈로 일부 실패) |
| `CF_Engine` | ✅ 완료 | — |
| `Vector_Search` | ✅ 완료 (CONTENT_BASED) | VISUAL_SIMILARITY 추가 가능 |
| `Normal_Recommendation` | ⚠️ 부족 | popular_recommendation 80건 → 재실행 필요 |
| `Hybrid_Layer` | 🔄 진행 중 | Phase 2 실행 중 → 3 → 4 순서로 완료 필요 |
| `API_Server` | ✅ 구현 완료 | 데이터 채워지면 바로 서빙 가능 |
| `Frontend` | — | API_Server 구동 후 연동 |
