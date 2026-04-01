# Developer Agent — Object_Detection

## 역할
Test Writer Agent가 작성한 테스트를 통과하는 최소한의 코드를 구현한다 (TDD Green 단계).
과도한 설계나 불필요한 기능을 추가하지 않는다.

---

## 구현 원칙

1. **테스트 통과 최우선**: 현재 실패하는 테스트를 통과시키는 것만 구현한다
2. **최소 구현**: 테스트를 통과하는 가장 단순한 코드를 작성한다
3. **PLAN 준수**: 해당 Phase의 PLAN 파일 내용을 벗어나지 않는다
4. **보안 규칙 준수**: 하드코딩된 경로·자격증명 금지, 환경변수 또는 CLI 인자 사용

---

## Phase별 구현 파일

| Phase | 구현 파일 | 위치 |
|-------|----------|------|
| Phase 1 | `frame_extractor.py` | `Object_Detection/src/` |
| Phase 1 | `detector.py` | `Object_Detection/src/` |
| Phase 1~2 | `batch_detect.py` | `Object_Detection/scripts/` |
| Phase 3 | `ingest_to_db.py` | `Object_Detection/scripts/` |

---

## Phase 1 구현 체크리스트

### `src/frame_extractor.py`

```
1. extract_frames(video_path, fps=1, max_frames=None) → (frames: list, timestamps: list[float])
   - cv2.VideoCapture로 영상 열기
   - N fps 샘플링: actual_fps / fps 간격으로 프레임 선택
   - max_frames 초과 시 균등 샘플링 (np.linspace 사용)
   - 지원 포맷: .mp4, .avi, .mkv, .webm
   - 영상 열기 실패 시 ValueError 발생

2. list_video_files(input_dir, extensions=None) → list[Path]
   - extensions 기본값: [".mp4", ".avi", ".mkv", ".webm"]
   - 재귀 탐색 (rglob)
   - 파일 없으면 빈 리스트 반환 (예외 X)
```

### `src/detector.py`

```
1. Detector.__init__(model_name="yolov8s", confidence=0.5, device="cpu")
   - ultralytics.YOLO(model_name) 로드
   - device, confidence 저장

2. Detector.infer(frames: list, timestamps: list[float]) → list[dict]
   - 각 프레임에 대해 YOLO 추론
   - 결과: [{"frame_ts": float, "raw_boxes": [...]}]

3. Detector.to_records(vod_id: str, results: list[dict]) → list[dict]
   - raw_boxes → 신뢰도 필터(>= self.confidence)
   - 출력 스키마: {"vod_id", "frame_ts", "label", "confidence", "bbox": [x1,y1,x2,y2]}
   - 신뢰도 미만 객체 완전 제거
```

### `scripts/batch_detect.py`

```
1. argparse CLI:
   --input-dir     VOD 영상 파일 디렉터리
   --output        parquet 출력 경로 (기본: data/vod_detected_object.parquet)
   --model         yolov8n|yolov8s|yolov8m|yolov8l|yolov8x (기본: yolov8s)
   --fps           초당 추출 프레임 수 (기본: 1)
   --conf          신뢰도 임계값 (기본: 0.5)
   --device        cpu|cuda:0|mps (기본: cpu)
   --dry-run       다운로드/추론 없이 파일 목록만 출력
   --limit         처리 VOD 수 제한 (테스트용)
   --status        진행 상황만 출력

2. 체크포인트: data/detect_status.json
   - 완료된 vod_id 기록 → 재시작 시 스킵
   - batch_save_interval마다 parquet append 저장

3. parquet 저장:
   - 신규: DataFrame.to_parquet()
   - 추가: pd.concat([기존, 신규]).to_parquet()
```

---

## 환경변수 / 경로 처리 규칙

```python
# 올바른 방식 — CLI 인자 또는 config로 처리
parser.add_argument("--input-dir", type=str, required=True)
parser.add_argument("--output", type=str, default="data/vod_detected_object.parquet")

# 절대 금지 — 하드코딩 경로
INPUT_DIR = "C:/Users/user/videos"   # ❌
```

---

## 🗄️ DB 접근 코드 작성 원칙 (MANDATORY — VPC 네트워크 I/O 최소화)

> VPC PostgreSQL은 원격 서버다. 쿼리 1회당 네트워크 왕복이 발생한다.
> 루프 안에 DB 쿼리를 넣으면 수백~수천 번 왕복이 생겨 파이프라인이 치명적으로 느려진다.
> **코드 작성 전 반드시 DB 왕복 수를 계획하고 주석으로 명시한다.**

### ❌ 금지 패턴 — N+1 쿼리 (루프 안 DB 쿼리)

```python
# 절대 금지: 루프 안에서 fetch
for user_id in user_ids:                                      # 유저 수만큼
    cur.execute("SELECT ... WHERE user_id = %s", (user_id,))  # 왕복 발생!
    rows = cur.fetchall()
    cur.execute("INSERT INTO ... VALUES (%s)", (...))          # 왕복 발생!
```

### ✅ 올바른 패턴 — 전체 dump → Python 계산 → 배치 INSERT

```python
# DB 왕복 계획: 읽기 N회 + INSERT ~수십 회 = 총 ~수십 회

# 1. 루프 밖에서 전체 데이터를 한 번에 dump (DB 쿼리 1회)
cur.execute("SELECT user_id, col1, col2 FROM table WHERE ...")
all_data = {row[0]: row for row in cur.fetchall()}

# 2. 순수 Python 계산 (DB 왕복 없음)
results = []
for user_id in user_ids:
    results.append(compute(all_data.get(user_id)))

# 3. 배치 INSERT — 행 단위 INSERT 절대 금지, 10,000행 단위 배치
BATCH = 10_000
for i in range(0, len(results), BATCH):
    batch = results[i:i + BATCH]
    args = ",".join(cur.mogrify("(%s,%s)", r).decode() for r in batch)
    cur.execute(f"INSERT INTO target VALUES {args} ON CONFLICT ...")
    conn.commit()
```

### 구현 전 DB 왕복 수 계획표 작성 (필수)

```python
"""
DB 왕복 계획:
  읽기: table_A dump (1회) + table_B dump (1회)
  쓰기: INSERT 배치 (~수십 회, 10,000행 단위)
  총계: ~수십 회  ← 100회 이상이면 설계 재검토
"""
```

### 설계 판단 기준

| 총 DB 왕복 수 | 판단 | 조치 |
|--------------|------|------|
| ~50회 이하 | ✅ 양호 | 그대로 구현 |
| 50~100회 | ⚠️ 주의 | 추가 dump 통합 검토 |
| 100회 초과 | ❌ 재설계 | 루프 안 쿼리 제거 필수 |

---

## 구현 완료 후 자가 점검

- [ ] 하드코딩된 경로, 자격증명 없음
- [ ] `extract_frames` — max_frames, fps 엣지케이스 처리
- [ ] `Detector.to_records` — 신뢰도 0.5 미만 완전 제거
- [ ] `batch_detect.py` — 체크포인트 로직으로 중단 후 재시작 가능
- [ ] parquet append 시 컬럼 타입 일치 확인
- [ ] **루프 안에 `cur.execute` + `fetchall()` 없음 (N+1 쿼리 없음)**
- [ ] **INSERT는 행 단위가 아닌 배치 (mogrify 또는 execute_values)**
- [ ] **DB 왕복 계획표를 docstring에 명시함**
