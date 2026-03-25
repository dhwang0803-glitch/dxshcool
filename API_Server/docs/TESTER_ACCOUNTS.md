# 테스터 계정 — JWT 토큰 발급 목록

> **⚠️ 배포 환경 변경 시 이 파일을 재생성하세요.**  
> `API_Server/scripts/gen_tester_tokens.py` 를 다시 실행하면 최신 JWT로 덮어씁니다.
> JWT는 만료 없음(셋톱박스 자동 로그인 정책). Secret이 바뀌면 모든 토큰 무효화.

**API Base URL**: `http://localhost:8000`  
**인증 방식**: `Authorization: Bearer <token>`

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