# Shopping_Ad 세션 리포트 — 2026-03-24

## 작업 요약

축제 광고 팝업 GIF 생성 + 제철장터 팝업 포맷 확정 + smry 기반 매칭 개선 + API_Server 연계 검토.

---

## 1. 축제 팝업 GIF — 최종 형식 확정

### 결정 사항
- **팝업(가로형)** 최종 채택 — 사진 배경 + 왼쪽 화이트 그라디언트 + 축제 정보
- overlay(SVG 일러스트), card(세로형 사진) 폐기
- 팀원 React 디자인을 순수 HTML/CSS/JS로 변환

### 폐기한 형식
| 형식 | 파일 | 폐기 이유 |
|------|------|-----------|
| overlay | `overlay_*.html` | 검정 배경이 VOD 위에서 부자연스러움 |
| card | `card_*.html` | 세로형(320x400)이 TV 화면에 안 어울림 |

### 최종 팝업 사양
- **크기**: 520x300 (HTML), VOD 삽입 시 130x76으로 축소
- **구조**: 배경 사진 + 왼쪽 화이트 그라디언트 + 축제명(34px) + 장소/일정(16px)
- **효과**: 배경 사진 느린 좌우 이동 + 축제별 CSS 파티클
- **CTA 버튼 제거** — GIF에서는 불필요

---

## 2. 축제 6건 GIF 생성 완료

| 축제 | HTML | 배경 사진 | CSS 효과 |
|------|------|----------|---------|
| 진해군항제 | popup_cherry_blossom.html | cherry_blossom.jpg | 벚꽃잎 흩날림 + 반짝이 |
| 단종문화제 | popup_danjong.html | danjong.jpg (Pexels) | 등불 글로우 + 빛 파티클 |
| 제주마 입목 | popup_jejuma.html | horses.jpg | 먼지 날림 |
| 해운대 모래축제 | popup_haeundae.html | beach_sand.jpg | 수면 반짝임 |
| 대덕물빛축제 | popup_mulbit.html | light_water.jpg | 빛 파티클 상승 |
| 춘천마임축제 | popup_mime.html | mime.jpg | 스포트라이트 회전 + 무대 먼지 |

- **GIF 출력**: `data/ad_gifs/popup_*.gif`
- **생성 명령**: `python scripts/generate_festival_gif.py`

---

## 3. VOD 영상 삽입 샘플

### 파이프라인
```
GIF → FFmpeg(stream_loop) → mp4 → setpts 타임시프트 + fade → VOD overlay
```

### 설정
- **대상 VOD**: food_altoran_496.mp4
- **트리거**: 891초 (14분 51초) — shopping_ad_candidates.parquet 기준
- **광고 크기**: 130x76 (우측 하단, 15px 마진)
- **페이드**: in 1.5초 / out 1.5초
- **생성 명령**: `python scripts/insert_ad_to_vod.py`

### 해결한 이슈
- PIL GIF 프레임 추출 → 검정 화면 문제 → FFmpeg `-stream_loop` 직접 변환으로 해결
- FFmpeg `enable='between(...)'` 타이밍 불일치 → `setpts=PTS+{TS}/TB` + `eof_action=pass`로 해결
- h264 홀수 해상도 에러 → 짝수(76px)로 수정

---

## 4. 코드 정리

### 삭제
- `templates/overlay_*.html` (6건)
- `templates/card_*.html` (6건)
- `data/ad_gifs/festival_*.gif` (overlay용 6건)
- `data/ad_gifs/card_*.gif` (카드용 6건)
- 임시 파일 (_tmp_*, test_*, sample_*)

### 수정
- `generate_festival_gif.py` — overlay/card 코드 제거, popup만 남김
- `insert_ad_to_vod.py` — popup 전용으로 단순화
- `CLAUDE.md` — 파일 구조, 현재 상태 업데이트

---

---

## 5. 제철장터 팝업 포맷 확정

### 결정 사항 (조장 합의)
- 방송 중/예정 2종 분기 — API_Server에서 현재시각 비교
- 버튼: [시청 하기]/[닫기] (방송 중), [시청 예약]/[닫기] (예정)
- 시청예약 → 알림 기능 연동은 조장이 설계

### 방송 중
```
지금 제철장터에서 {product_name} 판매 중입니다.
시청 하시겠습니까?
[시청 하기]  [닫기]
```

### 방송 예정
```
3월 25일(수) 제철장터에서 {product_name} 판매 예정입니다.
({start_time} ~ {end_time})
시청 예약 하시겠습니까?
[시청 예약]  [닫기]
```

> "오늘" → 정확한 방송 날짜(`3월 25일(수)`)로 변경.
> 제철장터는 주 단위 편성이므로 시청 당일이 아닌 다른 요일에도 안내 가능.

### 수정 파일
- `src/seasonal_matcher.py` — popup_title/popup_body → popup_text_live/popup_text_scheduled
- `docs/plans/PLAN_03_SEASONAL_POPUP_FORMAT.md` — 설계 문서

---

## 6. smry 기반 매칭 정확도 개선

### 구현 내용
- DB `public.vod.smry`에서 줄거리 19건 로드
- smry에서 지역명/음식 키워드 추출 → STT Top 3에 없는 키워드 보강
- 스코어링: 기본 1점 + smry 지역 일치 +2 + primary_region 일치 +1 + smry 음식 언급 +1

### 결과
- 건수 동일 (축제 6 + 제철장터 4 = 10건) — 제철장터 상품 10종이 한정적이라 추가 매칭 없음
- score 반영 확인: food_altoran_490(score=2), travel_dongwon_12(score=2)
- 재크롤링(4/7~8) 후 상품 늘어나면 smry 보강 효과 발생 예상

### 수정 파일
- `scripts/run_ad_matching.py` — smry 로드 + 스코어링 로직 추가
- `docs/plans/PLAN_04_SMRY_MATCHING.md` — 설계 문서

---

## 7. API_Server 연계 검토

### 데이터 흐름 확정
```
Shopping_Ad (데이터) → serving.shopping_ad
    → API_Server (WebSocket /ad/popup 전송 + 방송 중/예정 분기)
    → Frontend (팝업 렌더링 + 버튼)
```

### Shopping_Ad 책임 범위
- 매칭 로직 + 팝업 텍스트 생성 + serving.shopping_ad 적재 → **여기까지**
- WebSocket 전송, 실시간 분기 판단, UI 렌더링은 API_Server/Frontend 영역

### 연계 확인 결과
| 항목 | 상태 |
|------|------|
| 광고 타입 (local_gov/seasonal_market) | 일치 |
| WebSocket `/ad/popup` 스켈레톤 | API_Server에 구현됨 |
| 시청예약 API `POST /reservations` | 구현됨 (channel: int) |
| 제철장터 채널 번호 | 25번 확정 |
| 방송 중/예정 분기 | API_Server에서 처리 (조장 협의 중) |
| GIF 호스팅 방식 | 미정 (조장 협의 중) |

### 팝업 목업
- `templates/popup_seasonal_mockup.html` — 방송 중/예정 2종 VOD 프레임 위 시각화
- 대상: food_altoran_418 @ 379s (궁중동치미 클로즈업)

---

## 8. 남은 작업

| 항목 | 상태 | 비고 |
|------|------|------|
| 63건 전체 축제 GIF 자동 생성 | ✅ | 완료 |
| 제철장터 팝업 포맷 | ✅ | 방송 중/예정 2종 + 날짜 포맷 |
| smry 기반 매칭 개선 | ✅ | 스코어링 적용 |
| API_Server 연계 검토 | ✅ | 데이터 흐름 + 책임 범위 확정 |
| 팝업 목업 HTML | ✅ | VOD 프레임 위 시각 확인 |
| serving.shopping_ad DDL + 적재 | 🔲 | 조장 DB 작업 대기 |
| 제철장터 재크롤링 | 🔲 | 발표 전 (4/7~8) |
