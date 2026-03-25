# PLAN_04 — smry 기반 제철장터 매칭 정확도 개선

- **브랜치**: Shopping_Ad
- **작성일**: 2026-03-24

---

## 문제

현재 매칭 로직:
```
STT 음식 키워드 Top 3 → 제철장터 상품명 서브스트링 매칭 → 지역 우선 정렬
```

**한계**: VOD 줄거리(smry) 맥락을 무시한다.
- "영월 여행"에서 나온 "추어탕"인데, 지역 무관한 상품도 동일 우선순위로 매칭
- smry에 "회, 광어, 멍게"가 있는데 STT Top 3에 안 걸리면 해산물 상품 놓침

---

## 개선 방향

DB `public.vod` 테이블의 `smry` 컬럼을 활용하여 매칭 품질 향상.

### 1) smry에서 지역 추출 → 지역 매칭 보강

현재 `primary_region`은 Object_Detection 기반인데, smry에서도 지역을 추출하여 교차 검증.

```
smry: "장민호와 정동원이 강원도 영월을 찾아..."
→ 지역: 영월 (확정도 높음)
→ 제철장터 상품 중 영월/강원도 상품 우선
```

### 2) smry 음식 키워드 → 매칭 후보 확장

STT Top 3에 없지만 smry에 등장하는 음식으로 후보 확장.

```
smry: "옥돔구이, 흑돼지 제육 쌈밥, 백반, 귤 등 제주 맛집 탐방"
→ 추가 키워드: 옥돔구이, 흑돼지, 귤
→ 제철장터에 해당 상품 있으면 매칭 후보에 추가
```

### 3) smry 기반 매칭 스코어링

| 조건 | 점수 가산 |
|------|----------|
| STT Top 3 키워드 매칭 | 기본 점수 |
| + 상품 지역 == smry 지역 | +2 |
| + 상품 지역 == primary_region | +1 |
| + smry에 해당 음식 언급 | +1 |

점수 높은 순으로 정렬 → VOD당 1건 선택.

---

## 구현 범위

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `scripts/run_ad_matching.py` | smry 로드 + 스코어링 로직 추가, popup_title/popup_body → popup_text_live/popup_text_scheduled 반영 |
| `src/seasonal_matcher.py` | (완료) popup_text_live/popup_text_scheduled 포맷 |

### 데이터 흐름

```
DB vod.smry → 지역 추출 + 음식 키워드 추출
                ↓
STT Top 3 키워드 + smry 보강 키워드
                ↓
제철장터 매칭 → 스코어링 (지역 일치 + smry 언급 가산)
                ↓
VOD당 최고 점수 1건 선택
```

### DB 조회

```sql
SELECT full_asset_id, smry FROM public.vod
WHERE full_asset_id IN (대상 VOD 목록)
```

---

## 기대 효과

- 지역 정확도 향상: smry 지역과 상품 지역 교차 검증
- 매칭 범위 확장: STT에서 놓친 음식 키워드를 smry로 보완
- 스코어 기반 선택: 단순 첫 매칭이 아닌, 맥락 적합도 높은 상품 우선
