"""
Phase 2 테스트 — clip_scorer.py + location_tagger.py
TDD Red 단계: 구현 전 먼저 작성
"""
import pytest
import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ─────────────────────────────────────────
# 픽스처
# ─────────────────────────────────────────

@pytest.fixture(scope="session")
def sample_frame():
    """테스트용 더미 프레임 (320x240 BGR numpy)"""
    import numpy as np
    return np.zeros((240, 320, 3), dtype=np.uint8)


@pytest.fixture(scope="session")
def sample_frames():
    """프레임 3장"""
    return [np.zeros((240, 320, 3), dtype=np.uint8) for _ in range(3)]


@pytest.fixture(scope="session")
def clip_available():
    try:
        from sentence_transformers import SentenceTransformer
        return True
    except ImportError:
        return False


# ─────────────────────────────────────────
# clip_scorer 테스트
# ─────────────────────────────────────────

def test_P2_01_clip_scorer_import():
    """clip_scorer 모듈 import"""
    from clip_scorer import ClipScorer
    assert ClipScorer is not None


def test_P2_02_clip_scorer_init(clip_available):
    """ClipScorer 초기화"""
    if not clip_available:
        pytest.skip("sentence_transformers 미설치")
    from clip_scorer import ClipScorer
    scorer = ClipScorer()
    assert scorer is not None


def test_P2_03_score_frame_returns_dict(sample_frame, clip_available):
    """단일 프레임 + 쿼리 리스트 → dict 반환"""
    if not clip_available:
        pytest.skip("sentence_transformers 미설치")
    from clip_scorer import ClipScorer
    scorer = ClipScorer()
    queries = ["바닷가", "주방", "가전제품"]
    result = scorer.score_frame(sample_frame, queries)
    assert isinstance(result, dict)
    assert set(result.keys()) == set(queries)


def test_P2_04_score_range(sample_frame, clip_available):
    """score 값이 0~1 범위"""
    if not clip_available:
        pytest.skip("sentence_transformers 미설치")
    from clip_scorer import ClipScorer
    scorer = ClipScorer()
    queries = ["바닷가", "한식 식탁"]
    result = scorer.score_frame(sample_frame, queries)
    for q, score in result.items():
        assert 0.0 <= score <= 1.0, f"{q} score={score} 범위 초과"


def test_P2_05_score_frames_batch(sample_frames, clip_available):
    """여러 프레임 배치 처리 → 프레임별 dict 리스트"""
    if not clip_available:
        pytest.skip("sentence_transformers 미설치")
    from clip_scorer import ClipScorer
    scorer = ClipScorer()
    queries = ["바닷가", "주방"]
    results = scorer.score_frames(sample_frames, queries)
    assert isinstance(results, list)
    assert len(results) == len(sample_frames)
    for r in results:
        assert set(r.keys()) == set(queries)


def test_P2_06_empty_queries(sample_frame, clip_available):
    """빈 쿼리 리스트 → 빈 dict 반환 (예외 없음)"""
    if not clip_available:
        pytest.skip("sentence_transformers 미설치")
    from clip_scorer import ClipScorer
    scorer = ClipScorer()
    result = scorer.score_frame(sample_frame, [])
    assert result == {}


def test_P2_07_to_records(sample_frames, clip_available):
    """to_records → parquet 행 리스트 (vod_id, frame_ts, concept, clip_score)"""
    if not clip_available:
        pytest.skip("sentence_transformers 미설치")
    from clip_scorer import ClipScorer
    scorer = ClipScorer()
    queries = ["바닷가", "주방"]
    timestamps = [0.0, 1.0, 2.0]
    results = scorer.score_frames(sample_frames, queries)
    records = scorer.to_records("test_vod", timestamps, results, threshold=0.0)
    assert isinstance(records, list)
    for r in records:
        assert set(r.keys()) >= {"vod_id", "frame_ts", "concept", "clip_score"}


def test_P2_08_threshold_filter(sample_frames, clip_available):
    """threshold 이하 score 제거"""
    if not clip_available:
        pytest.skip("sentence_transformers 미설치")
    from clip_scorer import ClipScorer
    scorer = ClipScorer()
    queries = ["바닷가"]
    timestamps = [0.0, 1.0, 2.0]
    results = scorer.score_frames(sample_frames, queries)
    records = scorer.to_records("test_vod", timestamps, results, threshold=0.99)
    # threshold=0.99이면 더미 프레임에서 대부분 필터링됨
    for r in records:
        assert r["clip_score"] >= 0.99


# ─────────────────────────────────────────
# location_tagger 테스트
# ─────────────────────────────────────────

def test_P2_09_location_tagger_import():
    """location_tagger 모듈 import"""
    from location_tagger import LocationTagger
    assert LocationTagger is not None


def test_P2_10_random_location_range():
    """랜덤 위치 생성 — 한국 위경도 범위 내"""
    from location_tagger import LocationTagger
    tagger = LocationTagger()
    lat, lng = tagger.random_location()
    assert 33.0 <= lat <= 38.7, f"위도 범위 초과: {lat}"
    assert 124.5 <= lng <= 132.0, f"경도 범위 초과: {lng}"


def test_P2_11_location_to_region():
    """위경도 → 지역명(시/도) 반환"""
    from location_tagger import LocationTagger
    tagger = LocationTagger()
    region = tagger.get_region(37.5, 127.0)  # 서울 근방
    assert isinstance(region, str)
    assert len(region) > 0


def test_P2_12_region_to_ad_hint():
    """지역명 → 광고 카테고리 힌트 반환"""
    from location_tagger import LocationTagger
    tagger = LocationTagger()
    hints = tagger.get_ad_hints("전라남도")
    assert isinstance(hints, list)
    # 전남 → 굴비/김 등 특산물 포함 기대
    assert len(hints) >= 1


def test_P2_13_full_pipeline():
    """랜덤 위치 → 지역 → 광고 힌트 전체 파이프라인"""
    from location_tagger import LocationTagger
    tagger = LocationTagger()
    lat, lng = tagger.random_location()
    region = tagger.get_region(lat, lng)
    hints = tagger.get_ad_hints(region)
    assert isinstance(hints, list)
