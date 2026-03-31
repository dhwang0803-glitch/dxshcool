# 테스터 계정 — JWT 토큰 발급 목록

> **⚠️ 배포 환경 변경 시 이 파일을 재생성하세요.**
> `API_Server/scripts/gen_tester_tokens.py` 를 다시 실행하면 최신 JWT로 덮어씁니다.
> JWT는 만료 없음(셋톱박스 자동 로그인 정책). Secret이 바뀌면 모든 토큰 무효화.

**API Base URL**: `http://localhost:8000`
**인증 방식**: `Authorization: Bearer <token>`

---

## 테스터 격리 아키텍처

### 설계 원칙 (A+C 방식)

실 유저 추천 데이터(Jan↔Feb CF 평가 비교 대상)와 테스터 데이터를 완전히 격리한다.

```
public."user".is_test = TRUE  → *_test 격리 테이블 경유
public."user".is_test = FALSE → 기존 serving.* 테이블 (변경 없음)
```

**격리 테이블 구조:**
```
serving.vod_recommendation_test   ← CF_Engine 유사 유저 추천 복사
  ↓ Hybrid_Layer --test-mode
serving.hybrid_recommendation_test
serving.tag_recommendation_test
  ↓ API_Server (is_test 분기)
/recommend/{user_id}              ← 테스터는 자동으로 _test 테이블 서빙
```

**API_Server 분기 로직 (`recommend_service.py`):**
```python
is_test = await _is_test_user(pool, user_id)   # DB is_test 플래그 조회
hybrid_table = "serving.hybrid_recommendation_test" if is_test else "serving.hybrid_recommendation"
tag_table    = "serving.tag_recommendation_test"    if is_test else "serving.tag_recommendation"
```

---

### 추천 데이터 설정 방식

#### 유사 유저 복사 로직 (`CF_Engine/scripts/copy_similar_recommendations.py`)

테스터별로 ALS 학습에 사용된 실 유저 중 **Jaccard 유사도 최고** 유저를 탐색하여,
그 유저의 `serving.vod_recommendation`을 테스터 ID로 `serving.vod_recommendation_test`에 복사한다.

```
테스터 watch_history VOD 집합
  → 후보: 동일 VOD를 1개 이상 시청한 실 유저 (성능 필터)
  → Jaccard = |테스터 ∩ 실유저| / |테스터 ∪ 실유저|
  → 최고 유사도 유저의 vod_recommendation 행을 테스터 ID로 복사
  → serving.vod_recommendation_test ON CONFLICT DO UPDATE
```

#### Hybrid 파이프라인 (`Hybrid_Layer/scripts/run_pipeline.py --test-mode`)

```bash
# Phase 2: 테스터 watch_history × vod_tag → user_preference (is_test=TRUE 필터)
# Phase 3: vod_recommendation_test → hybrid_recommendation_test
# Phase 4: user_preference → tag_recommendation_test
python Hybrid_Layer/scripts/run_pipeline.py --test-mode
```

---

### 테스트 케이스 설계

테스터 12명을 **positive(추천 있음) 5명 + negative(fallback) 7명**으로 분리하여
정상 케이스와 fallback 케이스를 모두 검증한다.

#### ✅ Positive — 추천 데이터 있음 (5명)

`hybrid_recommendation_test` / `tag_recommendation_test` 데이터 존재 → 개인화 추천 정상 서빙

| 레이블 | User ID (앞 8자) | 특이사항 |
|--------|-----------------|---------|
| `C0_저관여_50대` | `f7328b31...` | C0 클러스터 대표 |
| `C1_충성_40대` | `877f7ce1...` | Shopping_Ad 19건 VOD watch_history 포함 |
| `C1_충성_60대` | `cf535eb5...` | 클래식·국악·다큐 선호 패턴 |
| `C2_헤비_50대` | `da3da6ae...` | C2 클러스터 대표, 헤비 시청 패턴 |
| `C3_키즈_40대` | `0486b86e...` | 키즈+성인 드라마 혼합 패턴 |

#### ❌ Negative — 추천 데이터 없음 (7명)

`hybrid_recommendation_test` 없음 → `popular_recommendation` fallback 서빙 확인

| 레이블 | User ID (앞 8자) | 테스트 목적 |
|--------|-----------------|------------|
| `C0_저관여_60대` | `077eec56...` | 완전 fallback (watch_history 있음) |
| `C1_충성_50대` | `248cfc7f...` | 완전 fallback |
| `C1_충성_30대` | `b2bc8285...` | 완전 fallback |
| `C2_헤비_40대` | `121aaaa7...` | 완전 fallback |
| `C2_헤비_30대` | `a8bfccc8...` | 완전 fallback |
| `C3_키즈_30대` | `afcc0aa5...` | 완전 fallback |
| `C3_키즈_60대` | `1dcc3e37...` | 완전 fallback |

---

### 추천 데이터 재생성 방법

```bash
# 1. 유사 유저 추천 복사 (CF_Engine 브랜치 체크아웃 후)
python CF_Engine/scripts/copy_similar_recommendations.py

# 2. 7명 fallback 유저 데이터 삭제 (5명만 유지) — DB 직접 실행
DELETE FROM serving.vod_recommendation_test
WHERE user_id_fk NOT IN (
  '877f7ce17f19e6e4503c13dc2b67e2e8b69d0830407cd53409a4907f25c7ee53',
  'da3da6ae52381ff5782832a3d908ce46057a5771d155dd690f2279b53455c79a',
  '0486b86e555429e746661fe3bb6b7f1b5aa57171bfdf06434777e0d359b36f1e',
  'f7328b318d191e3ef3ab456c7d7c8cc55ca85ff9f069ccd098f600a8e9561129',
  'cf535eb5910e56c5e597fff165a6e6ecf6eb17c28bf30a3b77739787b4120f18'
);

┌────────────────┬──────────────────────────────────────────────────────────────────┐                                                │     테스터     │                             user_id                              │
├────────────────┼──────────────────────────────────────────────────────────────────┤                                                 │ C0_저관여_50대 │ f7328b318d191e3ef3ab456c7d7c8cc55ca85ff9f069ccd098f600a8e9561129 │
├────────────────┼──────────────────────────────────────────────────────────────────┤                                                                            
│ C1_충성_40대   │ 877f7ce17f19e6e4503c13dc2b67e2e8b69d0830407cd53409a4907f25c7ee53 │
├────────────────┼──────────────────────────────────────────────────────────────────┤
│ C1_충성_60대   │ cf535eb5910e56c5e597fff165a6e6ecf6eb17c28bf30a3b77739787b4120f18 │
├────────────────┼──────────────────────────────────────────────────────────────────┤
│ C2_헤비_50대   │ da3da6ae52381ff5782832a3d908ce46057a5771d155dd690f2279b53455c79a │
├────────────────┼──────────────────────────────────────────────────────────────────┤
│ C3_키즈_40대   │ 0486b86e555429e746661fe3bb6b7f1b5aa57171bfdf06434777e0d359b36f1e └────────────────┴──────────────────────────────────────────────────────────────────┘

# 3. Hybrid 파이프라인 실행 (Hybrid_Layer 브랜치 체크아웃 후)
python Hybrid_Layer/scripts/run_pipeline.py --test-mode
```

---

## ✅ Positive 테스터 전체 User ID (빠른 복사용)

> `hybrid_recommendation_test` 데이터 있음 → 개인화 추천 정상 서빙

| 레이블 | Full User ID |
|--------|-------------|
| `C0_저관여_50대` | `f7328b318d191e3ef3ab456c7d7c8cc55ca85ff9f069ccd098f600a8e9561129` |
| `C1_충성_40대` | `877f7ce17f19e6e4503c13dc2b67e2e8b69d0830407cd53409a4907f25c7ee53` |
| `C1_충성_60대` | `cf535eb5910e56c5e597fff165a6e6ecf6eb17c28bf30a3b77739787b4120f18` |
| `C2_헤비_50대` | `da3da6ae52381ff5782832a3d908ce46057a5771d155dd690f2279b53455c79a` |
| `C3_키즈_40대` | `0486b86e555429e746661fe3bb6b7f1b5aa57171bfdf06434777e0d359b36f1e` |

**Base URL**: `https://vod-api-dev-121620013082.asia-northeast3.run.app`

```bash
# 예시 — C1_충성_40대 추천 조회
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  https://vod-api-dev-121620013082.asia-northeast3.run.app/recommend/877f7ce17f19e6e4503c13dc2b67e2e8b69d0830407cd53409a4907f25c7ee53
```

---

## 군집별 테스터 계정

### C0 — 저관여 (2명)

#### C0_저관여_50대
> 저관여 일반 시청자 — 드라마·예능 가끔 시청

| 항목 | 값 |
|------|----|
| **User ID** | `f7328b318d191e3ef3ab456c7d7c8cc55ca85ff9f069ccd098f600a8e9561129` |
| **JWT Token** | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |

**curl 예시:**
```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  http://localhost:8000/recommend/f7328b318d191e3ef3ab456c7d7c8cc55ca85ff9f069ccd098f600a8e9561129
```

#### C0_저관여_60대
> 저관여 일반 시청자 — 뉴스·교양 중심

| 항목 | 값 |
|------|----|
| **User ID** | `077eec56a021132c0ad3f7f94f1192d1821667258dfdcb00d9539a8f1bdfddc6` |
| **JWT Token** | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |

**curl 예시:**
```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  http://localhost:8000/recommend/077eec56a021132c0ad3f7f94f1192d1821667258dfdcb00d9539a8f1bdfddc6
```


### C1 — 충성 (4명)

#### C1_충성_50대
> 충성 시청자 — 주 4회 이상, 드라마·다큐 선호

| 항목 | 값 |
|------|----|
| **User ID** | `248cfc7fd82301adabc3d917908bf84ddb6b662362c0994ddccfa53a666eba75` |
| **JWT Token** | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |

**curl 예시:**
```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  http://localhost:8000/recommend/248cfc7fd82301adabc3d917908bf84ddb6b662362c0994ddccfa53a666eba75
```

#### C1_충성_40대
> 충성 시청자 — 시청 이력 50건, 다양한 장르

| 항목 | 값 |
|------|----|
| **User ID** | `877f7ce17f19e6e4503c13dc2b67e2e8b69d0830407cd53409a4907f25c7ee53` |
| **JWT Token** | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |

**curl 예시:**
```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  http://localhost:8000/recommend/877f7ce17f19e6e4503c13dc2b67e2e8b69d0830407cd53409a4907f25c7ee53
```

#### C1_충성_30대
> 충성 시청자 — OTT 병행, 트렌디 콘텐츠

| 항목 | 값 |
|------|----|
| **User ID** | `b2bc828585a6060181456f48c66f4981f6b56e4d7a689c398dc814a2e757dfdf` |
| **JWT Token** | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |

**curl 예시:**
```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  http://localhost:8000/recommend/b2bc828585a6060181456f48c66f4981f6b56e4d7a689c398dc814a2e757dfdf
```

#### C1_충성_60대
> 충성 시청자 — 클래식·국악·다큐 선호

| 항목 | 값 |
|------|----|
| **User ID** | `cf535eb5910e56c5e597fff165a6e6ecf6eb17c28bf30a3b77739787b4120f18` |
| **JWT Token** | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |

**curl 예시:**
```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  http://localhost:8000/recommend/cf535eb5910e56c5e597fff165a6e6ecf6eb17c28bf30a3b77739787b4120f18
```


### C2 — 헤비 유저 (3명)

#### C2_헤비_50대
> 헤비 유저 — 일 2시간 이상, SVOD 구독

| 항목 | 값 |
|------|----|
| **User ID** | `da3da6ae52381ff5782832a3d908ce46057a5771d155dd690f2279b53455c79a` |
| **JWT Token** | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |

**curl 예시:**
```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  http://localhost:8000/recommend/da3da6ae52381ff5782832a3d908ce46057a5771d155dd690f2279b53455c79a
```

#### C2_헤비_40대
> 헤비 유저 — 주말 정주행, 시리즈 완주율 높음

| 항목 | 값 |
|------|----|
| **User ID** | `121aaaa7a282ea0074187319a5ae05d81e0d96bb8d9dea4d8b0bb462c72b3007` |
| **JWT Token** | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |

**curl 예시:**
```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  http://localhost:8000/recommend/121aaaa7a282ea0074187319a5ae05d81e0d96bb8d9dea4d8b0bb462c72b3007
```

#### C2_헤비_30대
> 헤비 유저 — 장르 다양, 알림·찜 적극 활용

| 항목 | 값 |
|------|----|
| **User ID** | `a8bfccc82c6059f29ec89d359b9f09b45ed131d81bffd3d008d428bf0e135d6e` |
| **JWT Token** | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |

**curl 예시:**
```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  http://localhost:8000/recommend/a8bfccc82c6059f29ec89d359b9f09b45ed131d81bffd3d008d428bf0e135d6e
```


### C3 — 키즈 보호자 (3명)

#### C3_키즈_40대
> 키즈 보호자 — 어린이 콘텐츠 + 성인 드라마 병행

| 항목 | 값 |
|------|----|
| **User ID** | `0486b86e555429e746661fe3bb6b7f1b5aa57171bfdf06434777e0d359b36f1e` |
| **JWT Token** | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |

**curl 예시:**
```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  http://localhost:8000/recommend/0486b86e555429e746661fe3bb6b7f1b5aa57171bfdf06434777e0d359b36f1e
```

#### C3_키즈_30대
> 키즈 보호자 — 애니메이션·교육 프로그램 위주

| 항목 | 값 |
|------|----|
| **User ID** | `afcc0aa5c76c9db7f57d1e49877de0b6537c9cbf7b1c6fdc40d126a16ebaa4c0` |
| **JWT Token** | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |

**curl 예시:**
```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  http://localhost:8000/recommend/afcc0aa5c76c9db7f57d1e49877de0b6537c9cbf7b1c6fdc40d126a16ebaa4c0
```

#### C3_키즈_60대
> 키즈 보호자 — 손자녀 세대와 공동 시청

| 항목 | 값 |
|------|----|
| **User ID** | `1dcc3e37f935e439e95ee767f3873842872a6e9c68577e490a152f3f74bfff89` |
| **JWT Token** | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |

**curl 예시:**
```bash
curl -H "Authorization: Bearer <JWT_TOKEN>" \
  http://localhost:8000/recommend/1dcc3e37f935e439e95ee767f3873842872a6e9c68577e490a152f3f74bfff89
```

---

## 전체 토큰 요약표 (빠른 복사용)

| 레이블 | User ID (앞 8자) | JWT Token |
|--------|-----------------|-----------|
| `C0_저관여_50대` | `f7328b31...` | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |
| `C0_저관여_60대` | `077eec56...` | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |
| `C1_충성_50대` | `248cfc7f...` | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |
| `C1_충성_40대` | `877f7ce1...` | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |
| `C1_충성_30대` | `b2bc8285...` | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |
| `C1_충성_60대` | `cf535eb5...` | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |
| `C2_헤비_50대` | `da3da6ae...` | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |
| `C2_헤비_40대` | `121aaaa7...` | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |
| `C2_헤비_30대` | `a8bfccc8...` | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |
| `C3_키즈_40대` | `0486b86e...` | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |
| `C3_키즈_30대` | `afcc0aa5...` | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |
| `C3_키즈_60대` | `1dcc3e37...` | `⚠️ JWT_SECRET_KEY 설정 후 스크립트 재실행 필요` |

---

## 주요 테스트 엔드포인트

| 목적 | 엔드포인트 | 인증 |
|------|------------|------|
| 개인화 추천 | `GET /recommend/{user_id}` | 필요 |
| 홈 배너 | `GET /home/banner` | 선택 |
| 홈 섹션 | `GET /home/sections` | 불필요 |
| 개인화 섹션 | `GET /home/sections/{user_id}` | 필요 |
| VOD 검색 | `GET /vod/search?q={query}` | 불필요 |
| 시청 중 | `GET /user/me/watching` | 필요 |
| 시청 내역 | `GET /user/me/history` | 필요 |
| 찜 목록 | `GET /user/me/wishlist` | 필요 |
| 유사 콘텐츠 | `GET /similar/{asset_id}` | 불필요 |
| 포인트 | `GET /user/me/points` | 필요 |

---

*generated by `scripts/gen_tester_tokens.py`*