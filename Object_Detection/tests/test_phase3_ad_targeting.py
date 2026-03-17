"""
Phase 3 테스트 — ad_category + context_filter
TDD Red 단계: 구현 전 먼저 작성

테스트 대상:
  - src/context_filter.py  (ContextFilter)
  - clip_scorer.to_records() 에 ad_category 컬럼 추가
  - clip_queries_ko.yaml 구조 검증
"""
import pytest
import sys
import yaml
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

CONFIG_PATH = Path(__file__).parent.parent / "config" / "clip_queries_ko.yaml"


# ─────────────────────────────────────────
# 픽스처
# ─────────────────────────────────────────

@pytest.fixture(scope="session")
def config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def sample_frame():
    return np.zeros((240, 320, 3), dtype=np.uint8)


@pytest.fixture(scope="session")
def sample_frames():
    return [np.zeros((240, 320, 3), dtype=np.uint8) for _ in range(3)]


@pytest.fixture(scope="session")
def clip_available():
    try:
        from sentence_transformers import SentenceTransformer
        return True
    except ImportError:
        return False


# ─────────────────────────────────────────
# P3-01 ~ 03: clip_queries.yaml 구조 검증
# ─────────────────────────────────────────

def test_P3_01_required_categories_exist(config):
    """필수 카테고리 존재 여부 확인"""
    required = {"지방특산물", "과일채소", "여행지", "negative"}
    actual = set(config.get("queries", {}).keys())
    missing = required - actual
    assert not missing, f"누락된 카테고리: {missing}"


def test_P3_02_negative_category_has_queries(config):
    """negative 카테고리에 쿼리가 최소 1개 이상"""
    neg = config["queries"].get("negative", [])
    assert len(neg) >= 1, "negative 카테고리 쿼리 없음"


def test_P3_03_all_queries_are_strings(config):
    """모든 쿼리가 문자열"""
    for category, queries in config["queries"].items():
        for q in queries:
            assert isinstance(q, str), f"{category}: '{q}' 가 문자열이 아님"


# ─────────────────────────────────────────
# P3-04 ~ 06: ad_category 컬럼 검증
# ─────────────────────────────────────────

def test_P3_04_to_records_has_ad_category(sample_frames, clip_available):
    """to_records 결과에 ad_category 컬럼 포함"""
    if not clip_available:
        pytest.skip("sentence_transformers 미설치")
    from clip_scorer import ClipScorer
    scorer = ClipScorer()
    queries = ["Korean food dining table", "pineapple tropical fruit"]
    query_category_map = {
        "Korean food dining table": "한식",
        "pineapple tropical fruit": "과일채소",
    }
    timestamps = [0.0, 1.0, 2.0]
    results = scorer.score_frames(sample_frames, queries)
    records = scorer.to_records(
        "test_vod", timestamps, results,
        threshold=0.0,
        query_category_map=query_category_map,
    )
    for r in records:
        assert "ad_category" in r, "ad_category 컬럼 없음"


def test_P3_05_ad_category_matches_query(sample_frames, clip_available):
    """ad_category가 쿼리에 맞는 카테고리로 저장됨"""
    if not clip_available:
        pytest.skip("sentence_transformers 미설치")
    from clip_scorer import ClipScorer
    scorer = ClipScorer()
    queries = ["pineapple tropical fruit"]
    query_category_map = {"pineapple tropical fruit": "과일채소"}
    timestamps = [0.0]
    results = scorer.score_frames(sample_frames[:1], queries)
    records = scorer.to_records(
        "test_vod", timestamps, results,
        threshold=0.0,
        query_category_map=query_category_map,
    )
    for r in records:
        assert r["ad_category"] == "과일채소"


def test_P3_06_negative_category_records_excluded(sample_frames, clip_available):
    """negative 카테고리 쿼리는 records에서 제외"""
    if not clip_available:
        pytest.skip("sentence_transformers 미설치")
    from clip_scorer import ClipScorer
    scorer = ClipScorer()
    queries = ["Korean food dining table", "goldfish aquarium pet tank"]
    query_category_map = {
        "Korean food dining table": "한식",
        "goldfish aquarium pet tank": "negative",
    }
    timestamps = [0.0]
    results = scorer.score_frames(sample_frames[:1], queries)
    records = scorer.to_records(
        "test_vod", timestamps, results,
        threshold=0.0,
        query_category_map=query_category_map,
    )
    for r in records:
        assert r["ad_category"] != "negative", "negative 카테고리가 records에 포함됨"


# ─────────────────────────────────────────
# P3-07 ~ 11: context_filter 테스트
# ─────────────────────────────────────────

def test_P3_07_context_filter_import():
    """context_filter 모듈 import"""
    from context_filter import ContextFilter
    assert ContextFilter is not None


def test_P3_08_eating_scene_true():
    """생선 + 식기류 → context_valid=True"""
    from context_filter import ContextFilter
    cf = ContextFilter()
    yolo_labels = {"fish", "plate", "chopsticks", "person"}
    result = cf.validate(
        yolo_labels=yolo_labels,
        clip_scores={"person eating fish meal at dining table": 0.31},
        ad_category="지방특산물",
    )
    assert result["context_valid"] is True


def test_P3_09_aquarium_filtered():
    """금붕어 수조 → context_valid=False"""
    from context_filter import ContextFilter
    cf = ContextFilter()
    yolo_labels = {"fish"}  # 식기류 없음
    result = cf.validate(
        yolo_labels=yolo_labels,
        clip_scores={
            "goldfish aquarium pet tank": 0.38,
            "person eating fish meal at dining table": 0.09,
        },
        ad_category="지방특산물",
    )
    assert result["context_valid"] is False
    assert "aquarium" in result["context_reason"]


def test_P3_10_non_food_category_no_filter():
    """음식 외 카테고리(홈쇼핑/여행지)는 context 필터 미적용"""
    from context_filter import ContextFilter
    cf = ContextFilter()
    yolo_labels = {"couch", "tv"}
    result = cf.validate(
        yolo_labels=yolo_labels,
        clip_scores={"home appliance electronics TV": 0.29},
        ad_category="홈쇼핑",
    )
    assert result["context_valid"] is True


def test_P3_11_validate_returns_required_keys():
    """validate 반환값에 context_valid, context_reason 포함"""
    from context_filter import ContextFilter
    cf = ContextFilter()
    result = cf.validate(
        yolo_labels=set(),
        clip_scores={},
        ad_category="한식",
    )
    assert "context_valid" in result
    assert "context_reason" in result


def test_P3_12_global_negative_blocks_non_food():
    """Brand Safety(애니/재난)는 홈쇼핑 등 비음식 카테고리도 차단"""
    from context_filter import ContextFilter
    cf = ContextFilter()
    result = cf.validate(
        yolo_labels=set(),
        clip_scores={"만화 애니메이션 캐릭터 음식": 0.35, "가전제품 전자기기 TV": 0.28},
        ad_category="홈쇼핑",
    )
    assert result["context_valid"] is False
    assert "brand_safety" in result["context_reason"]


def test_P3_13_secondary_negative_check():
    """top-1이 아닌 negative 쿼리도 cutoff 이상이면 차단"""
    from context_filter import ContextFilter
    cf = ContextFilter()
    result = cf.validate(
        yolo_labels=set(),
        clip_scores={
            "굴비 먹는 식사 장면": 0.28,   # top-1 (positive)
            "낚시 낚싯대 강 물가": 0.23,   # 2nd (negative, cutoff 0.22 이상)
        },
        ad_category="지방특산물",
    )
    assert result["context_valid"] is False
    assert "secondary" in result["context_reason"]
