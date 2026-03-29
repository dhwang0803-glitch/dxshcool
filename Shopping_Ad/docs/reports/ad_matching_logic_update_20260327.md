# Shopping_Ad 매칭 로직 변경 보고서 (2026-03-29)

## 변경 파일

`Shopping_Ad/scripts/run_ad_matching.py`

---

## 1. 변경 배경

조장 피드백 (2026-03-27):

| 문제 | 원인 | 방향 |
|------|------|------|
| 6회 타이밍 477초 | 50% 최소 규칙이 도입부 풍경샷 무시 | 카테고리별 타이밍 분리 |
| 12회 아산↔삼척 지역 불일치 | 음식 키워드만으로 매칭 | 음식은 지역 무관으로 확정 (정상 동작) |
| 음식 클로즈업 시 광고 노출 | 50% 규칙이 앞쪽 클로즈업을 버림 | YOLO 탐지 프레임 즉시 사용 |
| OCR(자막) 있는 화면에서도 노출 | 기존 OCR 회피 로직 | OCR 필터 완전 제거 |

### 최종 합의된 매칭 원칙

| 카테고리 | 매칭 기준 | 지역 체크 |
|---------|----------|----------|
| **음식 → 제철장터** | 음식 키워드로 매칭 | 지역 무관 (스코어 가산만) |
| **관광지 → 축제** | 지역이 반드시 일치 | 불일치면 탈락 |

---

## 2. 변경 상세

### 2-1. 타이밍 함수 분리

**Before**: `find_clean_trigger_ts()` 1개 — 모든 카테고리에 동일 적용

```python
def find_clean_trigger_ts(parquet_dir, vod_id, min_pct=0.5):
    """영상 50% 이후 + OCR 없는 클린 구간의 frame_ts 찾기"""
```

**After**: 카테고리별 2개 함수로 분리

```python
def find_trigger_ts_food(parquet_dir, vod_id):
    """음식: YOLO 탐지 프레임 중 첫 밀집 구간"""

def find_trigger_ts_tour(parquet_dir, vod_id, min_pct=0.2):
    """관광지: CLIP 탐지 프레임 중 20% 이후 첫 밀집 구간"""
```

---

### 2-2. 음식 타이밍: `find_trigger_ts_food()`

**변경점**:
- `min_pct` 제거 (0.5 → 없음) — 영상 처음부터 후보
- OCR 회피 제거 — 자막 있어도 광고 노출
- YOLO 탐지 프레임 직접 사용

**로직**:

```
1. YOLO parquet에서 해당 VOD의 frame_ts 수집
2. 시간순 정렬
3. 밀집 구간 탐색: 30초 내 연속 2건 이상 탐지 = 실제 음식 장면
4. 첫 밀집 구간의 시작 프레임 = ts_start
5. 밀집 구간 없으면 첫 탐지 프레임 사용
6. YOLO 탐지 자체가 없으면 None (광고 없음)
```

**의도**: 음식이 화면에 클로즈업되는 순간 바로 광고 노출

**예시**:

```
food_altoran_490:
  Before: 50% 이후 구간 → 후반부
  After:  YOLO 첫 밀집 구간 → @1초 (영상 시작부터 음식 등장)
```

---

### 2-3. 관광지 타이밍: `find_trigger_ts_tour()`

**변경점**:
- `min_pct` 완화 (0.5 → 0.2) — 앞쪽 20%만 스킵 (타이틀 시퀀스 회피)
- OCR 회피 제거 — 자막 있어도 광고 노출
- CLIP 관광지 탐지 프레임 사용

**로직**:

```
1. CLIP parquet에서 해당 VOD의 관광지 카테고리 frame_ts 수집
2. max_ts * 0.2 이후 프레임만 필터
3. 밀집 구간 탐색: 30초 내 연속 2건 이상
4. 첫 밀집 구간의 시작 프레임 = ts_start
5. 밀집 구간 없으면 필터 후 첫 프레임 사용
6. CLIP 없으면 전체 max_ts * 0.2 지점 fallback
```

**의도**: 여행 영상은 도입부(타이틀/로고)만 피하고, 풍경 장면에서 빠르게 노출

**예시**:

```
travel_chonnom_01:
  Before: 50% 이후 → 후반부
  After:  20% 이후 CLIP 밀집 구간 → @105초
```

---

### 2-4. OCR(자막) 회피 로직 완전 제거

**Before**:

```python
# OCR이 있는 타임스탬프 수집
ocr_timestamps = set()
if ocr_path.exists():
    df_ocr = pd.read_parquet(str(ocr_path))
    vod_ocr = df_ocr[df_ocr["vod_id"] == vod_id]
    if len(vod_ocr) > 0:
        ocr_timestamps = set(vod_ocr["frame_ts"].round(0).astype(int).tolist())

# 이 구간에 OCR이 없는지 확인
has_ocr = any(t_start <= ts < t_end for ts in ocr_timestamps)
if not has_ocr:
    return float(t_start)
```

**After**: 삭제. OCR parquet을 아예 읽지 않음.

**이유**: 조장 요청 — 음식 클로즈업 시 자막이 있어도 광고 노출이 더 중요

---

### 2-5. score 로직 — 변경 없음

음식 매칭은 지역 무관으로 확정되었으므로 기존 스코어링 유지:

```python
score = 1                                    # 기본 (STT 키워드 매칭)
+ 상품 지역 == smry 지역:    +2              # 가산 (지역 일치 보너스)
+ 상품 지역 == primary_region: +1            # 가산
+ smry에 해당 음식 언급:      +1              # 가산
```

- 지역 일치 시 가산점 → 더 적절한 상품이 우선 선택됨
- 지역 불일치여도 **탈락하지 않음** → 매칭 자체는 허용
- 12회 삼척 VOD + 아산 닭갈비 → score 1~2로 매칭 OK (음식이 맞으니까)

---

## 3. 변경 전후 비교

### 파라미터 비교

| 항목 | Before | After |
|------|--------|-------|
| 타이밍 함수 | `find_clean_trigger_ts()` 1개 | `find_trigger_ts_food()` + `find_trigger_ts_tour()` 2개 |
| 음식 min_pct | 0.5 (50%) | 없음 (0%) |
| 관광지 min_pct | 0.5 (50%) | 0.2 (20%) |
| OCR 회피 | 있음 (자막 없는 구간만) | 제거 (자막 무관) |
| score 임계값 | 없음 | 없음 (음식은 지역 무관) |

### 실행 결과 비교 (타이밍 변화)

#### 제철장터 (음식)

| VOD | Before | After | 차이 |
|-----|--------|-------|------|
| `food_altoran_418` | 6분 16초 | **3분 18초** | -2분 58초 |
| `food_altoran_490` | 5분 27초 | **0분 01초** | -5분 26초 |
| `travel_chonnom_03` | 4분 57초 | 5분 13초 | +16초 |
| `travel_dongwon_12` | 3분 59초 | 7분 24초 | +3분 25초 |

#### 축제 (관광지)

| VOD | Before | After | 차이 |
|-----|--------|-------|------|
| `food_altoran_496` | 14분 51초 | **5분 56초** | -8분 55초 |
| `food_local_dakgalbi` | 6분 05초 | **2분 26초** | -3분 39초 |
| `travel_chonnom_01` | 4분 24초 | **1분 45초** | -2분 39초 |
| `travel_chonnom_07` | 5분 00초 | **2분 00초** | -3분 00초 |
| `travel_dongwon_06` | 16분 29초 | **7분 57초** | -8분 32초 |
| `travel_dongwon_16` | 13분 22초 | **5분 21초** | -8분 01초 |

### 매칭 건수 — 변경 없음

```
축제:     6건 (동일)
제철장터: 4건 (동일)
합계:    10건 (동일)
```

---

## 4. 안 바뀐 것

| 항목 | 상태 | 이유 |
|------|------|------|
| Object_Detection parquet 4종 | 그대로 | 탐지 결과는 정상, 해석만 변경 |
| `build_vod_summary.py` | 그대로 | VOD 요약 집계 로직 변경 없음 |
| `festival_matcher.py` | 그대로 | 지역 → 축제 매칭 (원래 지역 일치 필수) |
| `seasonal_matcher.py` | 그대로 | 키워드 → 상품 매칭 변경 없음 |
| `score_match()` | 그대로 | 지역 가산점 유지, 탈락 조건 없음 |
| 영상 재탐지 | 불필요 | parquet 재생성만 하면 됨 |

---

## 5. 버그 수정 (2026-03-29)

### 축제 candidate dict에 `region` 키 누락

- **증상**: 축제 후보 dict에 `"region"` 키가 없어 출력 루프에서 `KeyError` 발생
- **원인**: 제철장터 후보에는 `"region": primary_region`이 있었으나, 축제 후보에만 빠져있었음
- **수정**: `"region": f["region"]` 추가
- **parquet 영향**: `region` 컬럼이 축제 행에도 정상 포함됨

---

## 6. DB 제약조건 검증 (최종)

| CHECK 제약 | 결과 |
|-----------|------|
| NOT NULL 7개 컬럼 (`vod_id_fk`, `signal_source`, `score`, `ad_action_type`, `ad_category`, `ts_start`, `ts_end`) | ✅ null 0건 |
| `score` 0.0~1.0 | ✅ min=0.0545, max=1.0 |
| `signal_source` IN ('stt','clip','yolo','ocr') | ✅ 위반 0건 |
| `ad_action_type` IN ('local_gov_popup','seasonal_market') | ✅ |
| `ts_end >= ts_start` | ✅ 위반 0건 |
| `vod_id_fk` FK 형식 (cjc\|M...) | ✅ 10건 전부 |

---

## 7. 후속 작업

| 작업 | 담당 | 상태 |
|------|------|------|
| 새 parquet → 조장 전달 | 아름 | ✅ 재생성 완료 + PR #104 |
| `serving.shopping_ad` 재적재 | 조장 | 대기 |
| 시연용 VOD 선별 | 아름+조장 | 잘 매칭되는 VOD를 테스터 계정에 배치 |
| `travel_dongwon_06` 477초 | - | CLIP 탐지 후반부 밀집 → 시연에서 제외 권장 |
