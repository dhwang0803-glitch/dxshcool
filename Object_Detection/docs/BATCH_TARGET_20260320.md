# 배치 처리 대상 영상 목록 (2026-03-20)

> 조장님 지정. 시리즈별 4~5개, 총 19개.
> 기존 TMDB_NEW_2025 29건은 부적합 (트레일러 1분 미만 / 해외 여행 / 장르 오분류).

---

## 여행

### 동원아 여행가자 (5개)

| # | 회차 | 제목 | 선정 이유 | 링크 |
|---|------|------|-----------|------|
| 1 | 6화 | 사나이 여행 in 영월 | 국내 여행(영월) + 먹방 | [링크](https://youtu.be/fUDjJKcacdU) |
| 2 | 11화 | 동원아 정선가자 | 정선 여행 | [링크](https://youtu.be/sQEhu9y29qQ) |
| 3 | 12화 | 동원아 삼척 가자 | 삼척 여행 | [링크](https://youtu.be/8Q2kdaToxk0) |
| 4 | 16화 | 동원아 제주 가자 | 제주 여행 | [링크](https://youtu.be/KGjxaD-rdg0) |
| 5 | 15화 | 동원아 소고기 먹자 | 음식 중심 | [링크](https://youtu.be/pyraZGbe4y0) |

### 서울촌놈 (5개)

| # | 회차 | 지역 | 선정 이유 | 링크 |
|---|------|------|-----------|------|
| 1 | 1화 | 부산 | 해운대/자갈치 등 관광 키워드 풍부 | [링크](https://youtu.be/fqtBOF8kJrQ) |
| 2 | 3화 | 광주 | 광주 먹거리 + 관광 | [링크](https://youtu.be/mQXHy_ScL5I) |
| 3 | 5화 | 청주 | 충북 여행 | [링크](https://youtu.be/kcJuGQAGJGA) |
| 4 | 7화 | 대전 | 대전 여행 | [링크](https://youtu.be/-MM4DK5mW68) |
| 5 | 9화 | 전주 | 전주 한옥마을/먹방 키워드 최다 예상 | [링크](https://youtu.be/WLNlIm6UMm0) |

---

## 음식/먹방

### 알토란 (4개)

| # | 제목 | 링크 |
|---|------|------|
| 1 | 배추김치 [알토란 490회] | [링크](https://youtu.be/YkFCNmqNg4k) |
| 2 | 궁중동치미 비법 공개! [알토란 418회] | [링크](https://youtu.be/nz3ZeYyBVSQ) |
| 3 | 한우화산불고기 (천상현 레시피) [알토란 440회] | [링크](https://youtu.be/gjbXH09tZSw) |
| 4 | 순두부 대박집 비법 전수 [알토란 496회] | [링크](https://youtu.be/O2QvRLsNcrQ) |

### 로컬식탁 (5개) — 네이버 동영상

| # | 제목 | 링크 |
|---|------|------|
| 1 | 강원 내륙 메밀 막국수 한 상 | [링크](https://naver.me/GDQeRuuq) |
| 2 | 보령 키조개 한 상 | [링크](https://naver.me/xvC7elsP) |
| 3 | 삼치회를 가장 맛있게 즐기는 찐 로컬 방식 | [링크](https://naver.me/5WUlktId) |
| 4 | 원산도 수육국수 | [링크](https://naver.me/x3cg4VSB) |
| 5 | 진기주와 함께하는 춘천 닭갈비 | [링크](https://naver.me/5wrCI9fd) |

---

## 파일명 규칙

`data/batch_target/` 디렉토리에 저장:

```
여행:
  travel_dongwon_06.mp4    (영월)
  travel_dongwon_11.mp4    (정선)
  travel_dongwon_12.mp4    (삼척)
  travel_dongwon_16.mp4    (제주)
  travel_dongwon_15.mp4    (소고기)
  travel_chonnom_01.mp4    (부산)
  travel_chonnom_03.mp4    (광주)
  travel_chonnom_05.mp4    (청주)
  travel_chonnom_07.mp4    (대전)
  travel_chonnom_09.mp4    (전주)

음식_먹방:
  food_altoran_490.mp4     (배추김치)
  food_altoran_418.mp4     (궁중동치미)
  food_altoran_440.mp4     (한우화산불고기)
  food_altoran_496.mp4     (순두부)
  food_local_memill.mp4    (강원 메밀막국수) — 네이버 수동 다운로드
  food_local_keyjo.mp4     (보령 키조개) — 네이버 수동 다운로드
  food_local_samchi.mp4    (삼치회) — 네이버 수동 다운로드
  food_local_sugyuk.mp4    (원산도 수육국수) — 네이버 수동 다운로드
  food_local_dakgalbi.mp4  (춘천 닭갈비) — 네이버 수동 다운로드
```

## 배치 처리 순서

1. YouTube 14개 다운로드: `python scripts/download_batch_target.py`
2. 네이버 5개 수동 다운로드 → `data/batch_target/`에 저장
3. 배치 4종 실행 (YOLO + CLIP + STT + OCR)
4. VOD 요약 집계 → parquet 5개 생성
5. 조장님 전달
