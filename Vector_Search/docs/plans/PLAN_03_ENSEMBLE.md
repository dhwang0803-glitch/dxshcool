# PLAN_03: 앙상블 + 검색

**파일**: `src/ensemble.py`, `scripts/search.py`, `config/search_config.yaml`
**입력**: PLAN_01 content_score + PLAN_02 clip_score
**출력**: 최종 유사 콘텐츠 TOP-N 순위

---

## 앙상블 공식

```python
final_score = α * clip_score + (1 - α) * content_score
# α 초기값 = 0.4 (config/search_config.yaml에서 조정)
```

---

## 설정 파일 (`config/search_config.yaml`)

```yaml
ensemble:
  alpha: 0.4          # CLIP 가중치 (0~1), 나머지는 content_based
  top_n: 20           # 최종 반환 건수

search:
  ivfflat_probes: 10  # pgvector 검색 정확도
  sbert_model: "jhgan/ko-sroberta-multitask"
  clip_model: "clip-ViT-B-32"
```

---

## 구현 (`src/ensemble.py`)

```python
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config" / "search_config.yaml"

def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)

def ensemble_scores(
    clip_results: list[dict],
    content_results: list[dict],
    alpha: float,
    top_n: int,
) -> list[dict]:
    """
    두 결과를 vod_id 기준으로 합산 후 내림차순 정렬.
    clip_score / content_score 없는 경우 0으로 처리.
    """
    scores = {}

    for r in clip_results:
        scores.setdefault(r["vod_id"], {"clip_score": 0.0, "content_score": 0.0})
        scores[r["vod_id"]]["clip_score"] = r["clip_score"]

    for r in content_results:
        scores.setdefault(r["vod_id"], {"clip_score": 0.0, "content_score": 0.0})
        scores[r["vod_id"]]["content_score"] = r["content_score"]

    results = []
    for vod_id, s in scores.items():
        final = alpha * s["clip_score"] + (1 - alpha) * s["content_score"]
        results.append({
            "vod_id": vod_id,
            "final_score": round(final, 6),
            "clip_score": s["clip_score"],
            "content_score": s["content_score"],
        })

    return sorted(results, key=lambda x: x["final_score"], reverse=True)[:top_n]
```

---

## 검색 스크립트 (`scripts/search.py`)

```bash
# vod_id 기준 유사 콘텐츠 TOP-20 출력
python scripts/search.py --vod-id <full_asset_id>

# alpha 임시 override
python scripts/search.py --vod-id <full_asset_id> --alpha 0.6
```

---

**다음**: PLAN_04_DB_EXPORT.md
