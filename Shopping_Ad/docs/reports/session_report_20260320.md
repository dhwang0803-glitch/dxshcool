# Shopping_Ad 세션 리포트 — 2026-03-20

## 세션 요약

조장님 요청: Visit Korea 축제 사이트에서 4~5월 축제 크롤링 → Object_Detection region과 매칭 → 동작성 검증

## 작업 내역

### 1. Visit Korea 축제 크롤러 (`scripts/crawl_festivals.py`)
- API 엔드포인트 분석: `selectWntyFstvlList.do` (form-urlencoded POST)
- 파라미터: `searchDate=04월`, `startIdx` 페이지네이션
- 4월 88건 + 5월 120건 → 중복 제거 + 2026년 필터 → **63건 / 50개 지역**
- 산출물: `data/festivals.json`, `data/region_festivals.yaml`

### 2. 축제 매칭 엔진 (`src/festival_matcher.py`)
- region(지역명) → 축제 매칭
- 정확 매칭 + 부분 매칭 지원
- 팝업 데이터 생성 (popup_title, popup_body, ad_action_type)

### 3. E2E 검증 (`scripts/test_festival_match.py`)
- Object_Detection 테스트 영상 region 17개로 검증
- 결과: **7/17 매칭** (41%)

| 매칭 됨 | 축제 |
|---------|------|
| 부산 | 해운대 모래축제 |
| 경주 | 대릉원돌담길 축제 |
| 대전 | 대덕물빛축제 |
| 영월 | 단종문화제 |
| 제주 | 제주마 입목 문화축제 |
| 춘천 | 춘천마임축제 |
| 보령 | 홍성남당항 새조개축제 |

| 매칭 안 됨 | 이유 |
|-----------|------|
| 순천, 전주, 광주, 청주, 정선, 삼척, 여수 | 4~5월 축제 미등록 |

### 4. 문서 정리
- CLAUDE.md: 전략 변경 경고 추가
- PLAN_01_SHOPPING_AD.md: OUTDATED 경고
- PLAN_01_MATCHER.md: OUTDATED 경고

## 동작성 검증 결론

- **매칭 로직 정상 동작**: region → 축제 연결 확인
- **커버리지 한계**: Visit Korea 4~5월 등록 축제가 50개 지역에만 있음
- **해결 방안**: 조장님 계획대로 생성형 AI로 축제 없는 지역도 관광 팝업 생성 예정

## 다음 작업

1. Object_Detection 배치 5개 테스트 결과 확인
2. 제철장터 매칭 로직 (음식 ad_category → 제철장터 상품)
3. serving.shopping_ad 적재 스크립트
4. 전체 19개 배치 처리 + parquet 생성
