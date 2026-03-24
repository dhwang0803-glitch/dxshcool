# Shopping_Ad 세션 리포트 — 2026-03-24

## 작업 요약

축제 광고 팝업 GIF 생성 파이프라인 완성 및 VOD 영상 삽입 샘플 제작.

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

## 5. 남은 작업

| 항목 | 상태 | 비고 |
|------|------|------|
| 63건 전체 축제 GIF 자동 생성 | 🔲 | 템플릿 파라미터화 + 테마별 공용 사진 |
| serving.shopping_ad DDL + 적재 | 🔲 | 조장 DB 작업 대기 |
| 제철장터 재크롤링 | 🔲 | 발표 전 (4/7~8) |
| 축제 재크롤링 | 🔲 | 발표 전 (4/7~8) |
| 매칭 정확도 개선 (smry 기반) | 🔲 | 조장 DB에 smry 채운 후 |
