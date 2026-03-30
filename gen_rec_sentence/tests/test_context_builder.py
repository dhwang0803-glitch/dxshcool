"""context_builder.py 단위 테스트."""

import pytest
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, ".")

from gen_rec_sentence.src.context_builder import _parse_embedding, build_prompt


class TestParseEmbedding:
    def test_none_returns_empty(self):
        assert _parse_embedding(None) == []

    def test_list_passthrough(self):
        vec = [0.1, 0.2, 0.3]
        assert _parse_embedding(vec) == vec

    def test_string_format(self):
        result = _parse_embedding("[0.1, 0.2, 0.3]")
        assert len(result) == 3
        assert abs(result[0] - 0.1) < 1e-5


class TestBuildPrompt:
    def test_basic_substitution(self):
        ctx = {
            "asset_nm": "덩케르크", "genre": "전쟁", "genre_detail": "액션",
            "director": "크리스토퍼 놀란", "cast_lead": "킬리언 머피",
            "smry": "2차 세계대전...", "rating": "12세", "embedding": [0.1] * 512,
        }
        template = "제목: {asset_nm} 감독: {director}"
        result = build_prompt(ctx, template)
        assert "덩케르크" in result
        assert "크리스토퍼 놀란" in result
