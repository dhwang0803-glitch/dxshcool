# PLAN_03 — 제철장터 팝업 문구 포맷 설계

- **브랜치**: Shopping_Ad
- **작성일**: 2026-03-24
- **합의**: 황대원(조장) + 박아름

---

## 배경

VOD 시청 중 음식 키워드가 탐지되면 제철장터 상품 매칭 팝업을 노출한다.
시청 시점의 방송 상태에 따라 2가지 포맷으로 분기한다.

---

## 팝업 포맷 (2종)

### 1) 방송 중 (실시간)

시청 시점이 `start_time ~ end_time` 범위 안일 때:

```
지금 제철장터에서 {product_name} 판매 중입니다.
시청 하시겠습니까?

[시청 하기]  [닫기]
```

### 2) 방송 예정

시청 시점이 `start_time` 이전일 때 (당일 또는 그 주 내):

```
3월 26일(수) 제철장터에서 {product_name} 판매 예정입니다.
({start_time} ~ {end_time})

시청 예약 하시겠습니까?

[시청 예약]  [닫기]
```

> 제철장터는 주 단위 편성이므로, 시청 당일이 아닌 다른 요일에도 방송 예정 안내를 띄운다.
> Shopping_Ad는 항상 정확한 방송 날짜(`3월 26일(수)`)를 포함하여 전달한다.

---

## 변수 매핑

| 변수 | 소스 | 예시 |
|------|------|------|
| `{product_name}` | `seasonal_market.json` → `product_name` | 남원추어탕 |
| `{broadcast_date}` | `seasonal_market.json` → `broadcast_date` → `_format_date()` | 3월 26일(수) |
| `{start_time}` | `seasonal_market.json` → `start_time` | 14:00 |
| `{end_time}` | `seasonal_market.json` → `end_time` | 15:00 |

---

## 역할 분담

| 담당 | 작업 |
|------|------|
| **Shopping_Ad** (박아름) | 두 포맷 템플릿 정의 + 상품명/채널/시간 데이터 제공 |
| **API_Server** (황대원) | 현재시각 vs start_time~end_time 비교 → 분기 판단, 시청예약 → 알림 기능 연동 로직 설계 |
| **Frontend** | 버튼 렌더링 ([시청 하기]/[시청 예약]/[닫기]) |

---

## 구현 범위 (Shopping_Ad)

1. `src/seasonal_matcher.py`의 `_enrich` 메서드에 두 포맷 템플릿 추가
2. `popup_text_live` (방송 중), `popup_text_scheduled` (예정) 두 필드로 제공
3. 분기 판단은 하지 않음 — API_Server에서 시청 시점 기준으로 선택

---

## 참고

- 버튼 동작(시청예약 → 알림 업데이트)은 황대원 조장이 설계 예정
- 포맷은 채널명/시간/품목명 파싱으로 충분 (황대원 확인, 2026-03-24)
