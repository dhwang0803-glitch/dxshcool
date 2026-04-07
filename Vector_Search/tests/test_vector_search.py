"""
Vector_Search 핵심 함수 단위 테스트

실행:
    pytest Vector_Search/tests/test_vector_search.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, ".")

from scripts.evaluate_precision import genre_match, calc_precision_at_k
from Vector_Search.src.ensemble import EnsembleScorer, ensemble_scores, load_config
from Vector_Search.src.base import VectorSearchBase
from Vector_Search.src.clip_based import ClipSearcher, clip_searcher
from Vector_Search.src.content_based import ContentSearcher, content_searcher
from Vector_Search.src.visual_similarity import (
    VisualSimilarity, visual_similarity, get_visual_recommendations,
)


# ──────────────────────────────────────────────
# genre_match 테스트
# ──────────────────────────────────────────────

class TestGenreMatch:
    def test_exact_match(self):
        """동일 장르 → True"""
        assert genre_match("드라마", "드라마") is True

    def test_partial_match(self):
        """복합 장르 중 하나라도 겹치면 → True"""
        assert genre_match("로맨스/드라마", "드라마/스릴러") is True

    def test_no_match(self):
        """겹치는 장르 없음 → False"""
        assert genre_match("액션/SF", "로맨스/드라마") is False

    def test_src_empty(self):
        """기준 장르 비어있으면 → False"""
        assert genre_match("", "드라마") is False

    def test_tgt_empty(self):
        """추천 장르 비어있으면 → False"""
        assert genre_match("드라마", "") is False

    def test_both_empty(self):
        """둘 다 비어있으면 → False"""
        assert genre_match("", "") is False

    def test_none_value(self):
        """None 값 → False"""
        assert genre_match(None, "드라마") is False

    def test_whitespace_strip(self):
        """공백 포함 장르 → strip 후 비교"""
        assert genre_match("드라마 / 로맨스", "드라마") is True


# ──────────────────────────────────────────────
# EnsembleScorer 테스트
# ──────────────────────────────────────────────

class TestEnsembleScores:
    def test_basic_ensemble(self):
        """기본 앙상블 — clip + content 정상 합산"""
        clip = [{"vod_id": "A", "clip_score": 0.8}]
        content = [{"vod_id": "A", "content_score": 0.6}]
        result = EnsembleScorer.score(clip, content, alpha=0.4, top_n=5)
        assert len(result) == 1
        expected = round(0.4 * 0.8 + 0.6 * 0.6, 6)
        assert result[0]["final_score"] == expected

    def test_no_clip_score(self):
        """clip_score 없는 VOD → alpha=0, content_score 100% 반영"""
        content = [{"vod_id": "B", "content_score": 0.7}]
        result = EnsembleScorer.score([], content, alpha=0.4, top_n=5)
        assert result[0]["final_score"] == 0.7

    def test_sorted_by_score(self):
        """결과가 final_score 내림차순으로 정렬되어야 함"""
        clip = [
            {"vod_id": "A", "clip_score": 0.5},
            {"vod_id": "B", "clip_score": 0.9},
        ]
        content = [
            {"vod_id": "A", "content_score": 0.5},
            {"vod_id": "B", "content_score": 0.9},
        ]
        result = EnsembleScorer.score(clip, content, alpha=0.4, top_n=5)
        assert result[0]["vod_id"] == "B"
        assert result[1]["vod_id"] == "A"

    def test_top_n_limit(self):
        """top_n 개수 제한 적용"""
        content = [{"vod_id": str(i), "content_score": i / 10} for i in range(10)]
        result = EnsembleScorer.score([], content, alpha=0.4, top_n=3)
        assert len(result) == 3

    def test_clip_score_1_treated_as_no_clip(self):
        """clip_score=1.0 (시즌물 동일 트레일러) — ensemble에서는 alpha 적용됨"""
        clip = [{"vod_id": "C", "clip_score": 1.0}]
        content = [{"vod_id": "C", "content_score": 0.8}]
        result = EnsembleScorer.score(clip, content, alpha=0.4, top_n=5)
        expected = round(0.4 * 1.0 + 0.6 * 0.8, 6)
        assert result[0]["final_score"] == expected

    def test_empty_inputs(self):
        """입력 비어있으면 빈 리스트 반환"""
        result = EnsembleScorer.score([], [], alpha=0.4, top_n=5)
        assert result == []

    def test_backward_compat_alias(self):
        """ensemble_scores 별칭 동작 확인"""
        result = ensemble_scores([], [], alpha=0.4, top_n=5)
        assert result == []


# ──────────────────────────────────────────────
# load_config 테스트
# ──────────────────────────────────────────────

class TestLoadConfig:
    def test_config_keys_exist(self):
        """필수 키 존재 확인"""
        config = VectorSearchBase.load_config()
        assert "ensemble" in config
        assert "search" in config

    def test_alpha_value(self):
        """alpha=0.4 설정값 확인"""
        config = VectorSearchBase.load_config()
        assert config["ensemble"]["alpha"] == 0.4

    def test_top_n_value(self):
        """top_n=20 설정값 확인"""
        config = VectorSearchBase.load_config()
        assert config["ensemble"]["top_n"] == 20

    def test_load_config_alias(self):
        """각 모듈의 load_config 별칭이 동일한 함수를 참조"""
        assert load_config is VectorSearchBase.load_config


# ──────────────────────────────────────────────
# calc_precision_at_k 테스트
# ──────────────────────────────────────────────

class TestCalcPrecisionAtK:
    def _make_rec_df(self):
        return pd.DataFrame([
            {"source_vod_id": "src1", "vod_id_fk": "tgt1", "rank": 1},
            {"source_vod_id": "src1", "vod_id_fk": "tgt2", "rank": 2},
            {"source_vod_id": "src1", "vod_id_fk": "tgt3", "rank": 3},
        ])

    def _make_meta_df(self, genre_map):
        df = pd.DataFrame([
            {"vod_id": k, "genre": v} for k, v in genre_map.items()
        ]).set_index("vod_id")
        return df

    def test_perfect_precision(self):
        """모든 추천이 같은 장르 → Precision=1.0"""
        rec_df = self._make_rec_df()
        meta_df = self._make_meta_df({
            "src1": "드라마", "tgt1": "드라마", "tgt2": "드라마", "tgt3": "드라마"
        })
        result = calc_precision_at_k(rec_df, meta_df, "genre", k=3, sample=None)
        assert result == 1.0

    def test_zero_precision(self):
        """추천이 모두 다른 장르 → Precision=0.0"""
        rec_df = self._make_rec_df()
        meta_df = self._make_meta_df({
            "src1": "드라마", "tgt1": "액션", "tgt2": "SF", "tgt3": "공포"
        })
        result = calc_precision_at_k(rec_df, meta_df, "genre", k=3, sample=None)
        assert result == 0.0

    def test_partial_precision(self):
        """절반만 일치 → Precision=0.5 (k=2 기준)"""
        rec_df = self._make_rec_df()
        meta_df = self._make_meta_df({
            "src1": "드라마", "tgt1": "드라마", "tgt2": "액션", "tgt3": "드라마"
        })
        result = calc_precision_at_k(rec_df, meta_df, "genre", k=2, sample=None)
        assert result == 0.5


# ──────────────────────────────────────────────
# 클래스 구조 테스트
# ──────────────────────────────────────────────

class TestClassStructure:
    def test_all_inherit_base(self):
        for cls in [ClipSearcher, ContentSearcher, EnsembleScorer]:
            assert issubclass(cls, VectorSearchBase), f"{cls.__name__} must inherit VectorSearchBase"

    def test_singleton_instances(self):
        assert isinstance(clip_searcher, ClipSearcher)
        assert isinstance(content_searcher, ContentSearcher)

    def test_clip_alias(self):
        from Vector_Search.src.clip_based import get_similar_by_clip
        assert get_similar_by_clip == clip_searcher.search

    def test_content_alias(self):
        from Vector_Search.src.content_based import get_similar_by_meta
        assert get_similar_by_meta == content_searcher.search

    def test_ensemble_alias(self):
        assert ensemble_scores is EnsembleScorer.score

    def test_db_get_connection_exists(self):
        from Vector_Search.src.db import get_connection
        assert callable(get_connection)


# ──────────────────────────────────────────────
# VisualSimilarity 클래스 테스트
# ──────────────────────────────────────────────

class TestVisualSimilarity:
    def test_inherits_base(self):
        """VectorSearchBase 상속 확인"""
        assert issubclass(VisualSimilarity, VectorSearchBase)

    def test_singleton_instance(self):
        """모듈 레벨 싱글턴 확인"""
        assert isinstance(visual_similarity, VisualSimilarity)

    def test_alias(self):
        """get_visual_recommendations 별칭 동작 확인"""
        assert get_visual_recommendations == visual_similarity.search

    def test_extract_clip_vector_shape(self):
        """896D → 512D CLIP 벡터 추출"""
        import numpy as np
        vec_896 = np.random.randn(896).astype(np.float32)
        clip_vec = VisualSimilarity.extract_clip_vector(vec_896)
        assert len(clip_vec) == 512
        assert np.array_equal(clip_vec, vec_896[:512])

    def test_extract_clip_vector_independence(self):
        """CLIP 부분과 META 부분이 독립적으로 추출되는지 확인"""
        import numpy as np
        vec = np.zeros(896, dtype=np.float32)
        vec[:512] = 1.0   # CLIP part
        vec[512:] = 2.0   # META part
        clip = VisualSimilarity.extract_clip_vector(vec)
        assert all(v == 1.0 for v in clip)
        assert len(clip) == 512


class TestVisualSimilarityConfig:
    def test_config_section_exists(self):
        """visual_similarity 설정 키 존재"""
        config = VectorSearchBase.load_config()
        assert "visual_similarity" in config

    def test_top_n_value(self):
        """top_n=20 기본값 확인"""
        config = VectorSearchBase.load_config()
        assert config["visual_similarity"]["top_n"] == 20

    def test_clip_dim_value(self):
        """clip_dim=512 확인"""
        config = VectorSearchBase.load_config()
        assert config["visual_similarity"]["clip_dim"] == 512
