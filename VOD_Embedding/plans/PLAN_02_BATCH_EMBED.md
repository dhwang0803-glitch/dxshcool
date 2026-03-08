# PLAN_02: CLIP 배치 임베딩

**브랜치**: VOD_Embedding
**스크립트**: `pipeline/batch_embed.py`
**입력**: `trailers/*.webm`, `data/crawl_status.json`
**출력**: `data/video_embs_batch_*.pkl`, `data/embed_status.json`

---

## 목표

PLAN_01에서 수집한 트레일러 영상에 대해:
1. OpenCV로 10프레임 균등 추출
2. CLIP ViT-B/32로 프레임별 512차원 벡터 생성
3. 10개 벡터 평균 → VOD 대표 벡터
4. 1,000개 단위 배치로 pkl 저장

---

## 모델 설정

```python
MODEL_PATH = "C:/Users/daewo/DX_prod_2nd/my_clip_model"
# sentence-transformers 방식으로 로드
from sentence_transformers import SentenceTransformer
model = SentenceTransformer(MODEL_PATH)
```

> 모델이 로컬에 없을 경우 자동 다운로드:
> `SentenceTransformer('clip-ViT-B-32')` → HuggingFace Hub에서 받아 로컬 캐시

---

## 프레임 추출 및 임베딩 방법

```python
import cv2
import numpy as np
from PIL import Image

N_FRAMES = 10  # 균등 추출 프레임 수

def extract_frames(video_path: str) -> list[Image.Image]:
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps   = cap.get(cv2.CAP_PROP_FPS)

    if total <= 0 or fps <= 0:
        cap.release()
        raise ValueError(f"유효하지 않은 영상: {video_path}")

    indices = np.linspace(0, total - 1, N_FRAMES, dtype=int)
    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            # BGR → RGB → PIL
            frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    cap.release()
    return frames

def get_video_embedding(video_path: str, model) -> np.ndarray:
    frames = extract_frames(video_path)
    if not frames:
        raise ValueError("프레임 추출 실패")
    vectors = model.encode(frames, convert_to_numpy=True, show_progress_bar=False)
    return vectors.mean(axis=0).astype(np.float32)  # shape: (512,)
```

---

## 배치 처리 전략

- 배치 크기: **1,000개** (`BATCH_SIZE = 1000`)
- 배치 파일명: `data/video_embs_batch_001.pkl`, `_002.pkl`, ...
- 체크포인트: 배치 완료 시 `data/embed_status.json` 갱신

### pkl 저장 포맷

```python
# 배치 하나 = List[dict]
batch = [
    {
        "vod_id": "VOD001234",          # full_asset_id
        "title": "어바웃 타임",           # asset_nm
        "video_file": "dQw4w9WgXcQ.webm",
        "vector": np.array([...], dtype=np.float32),  # shape (512,)
        "magnitude": float,              # 품질 지표
        "embedded_at": "2026-03-08T14:00:00",
    },
    ...
]
with open("data/video_embs_batch_001.pkl", "wb") as f:
    pickle.dump(batch, f)
```

---

## 체크포인트 구조 (`data/embed_status.json`)

```json
{
  "last_updated": "2026-03-08T15:00:00",
  "total_trailers": 28000,
  "processed": 5000,
  "success": 4900,
  "failed": 100,
  "batches_completed": ["video_embs_batch_001.pkl", "video_embs_batch_002.pkl"],
  "failed_vods": {
    "VOD009999": "프레임 추출 실패: 영상 손상"
  }
}
```

---

## 품질 관리

```python
def check_vector_quality(vec: np.ndarray) -> bool:
    mag = np.linalg.norm(vec)
    if mag < 0.01:
        return False   # 영벡터 — 이상
    if mag > 100.0:
        return False   # 극단값
    return True
```

이상 벡터는 `failed_vods`에 기록하고 해당 VOD 스킵.

---

## GPU/CPU 설정

| 환경 | 처리 속도 |
|------|----------|
| GPU (CUDA) | 100개/분 |
| CPU only | 10~15개/분 |

CPU 환경 기준 28,000개: **약 33~47시간** (오버나이트 실행)

```python
import torch
device = "cuda" if torch.cuda.is_available() else "cpu"
# SentenceTransformer는 device 자동 감지
```

---

## 실행 방법

```bash
conda activate myenv

# 전체 실행 (자동 재시작 지원)
python pipeline/batch_embed.py

# 특정 배치 범위만 처리
python pipeline/batch_embed.py --start-batch 3 --end-batch 10

# 진행 상황 확인
python pipeline/batch_embed.py --status
```

---

## 디렉토리 구조 (완료 후)

```
data/
├── embed_status.json
├── video_embs_batch_001.pkl   # vod_id 1~1000
├── video_embs_batch_002.pkl   # vod_id 1001~2000
├── ...
└── video_embs_batch_028.pkl   # 마지막 배치
```

---

**다음**: PLAN_03_DB_INGEST.md
