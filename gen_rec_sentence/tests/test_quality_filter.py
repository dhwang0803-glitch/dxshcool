"""quality_filter.py 단위 테스트."""

import sys
sys.path.insert(0, ".")

from gen_rec_sentence.src.quality_filter import validate, filter_batch


_CTX = {
    "vod_id": "test_001",
    "asset_nm": "덩케르크",
    "genre": "전쟁",
    "smry": "2차 세계대전, 덩케르크 해변에 고립된 40만 연합군 병사들의 탈출 작전을 다룬 영화.",
}


class TestValidate:
    def test_pass_normal(self):
        result = validate({"vod_id": "test_001", "rec_sentence": "총알이 빗발치는 해변, 탈출을 위한 필사적인 항해.\n하늘을 덮은 적의 그림자."}, _CTX)
        assert result["pass"] is True
        assert result["fail_reasons"] == []

    def test_fail_empty(self):
        result = validate({"vod_id": "test_001", "rec_sentence": ""}, _CTX)
        assert result["pass"] is False
        assert "empty" in result["fail_reasons"]

    def test_fail_too_short(self):
        result = validate({"vod_id": "test_001", "rec_sentence": "짧은 문구"}, _CTX)
        assert result["pass"] is False
        assert any("too_short" in r for r in result["fail_reasons"])

    def test_fail_too_long(self):
        result = validate({"vod_id": "test_001", "rec_sentence": "가" * 121}, _CTX)
        assert result["pass"] is False
        assert any("too_long" in r for r in result["fail_reasons"])

    def test_fail_forbidden_word(self):
        result = validate({"vod_id": "test_001", "rec_sentence": "역대급 스케일의 전쟁 영화, 놀란 감독의 걸작이 찾아왔다."}, _CTX)
        assert result["pass"] is False
        assert any("forbidden" in r for r in result["fail_reasons"])

    def test_fail_none_sentence(self):
        result = validate({"vod_id": "test_001", "rec_sentence": None}, _CTX)
        assert result["pass"] is False


class TestFilterBatch:
    def test_split_pass_fail(self):
        results = [
            {"vod_id": "test_001", "rec_sentence": "총알이 빗발치는 해변, 탈출을 위한 필사적인 항해.\n하늘을 덮은 적의 그림자."},
            {"vod_id": "test_002", "rec_sentence": "짧음"},
        ]
        contexts = [_CTX, {**_CTX, "vod_id": "test_002"}]
        passed, failed = filter_batch(results, contexts)
        assert len(passed) == 1
        assert len(failed) == 1
        assert passed[0]["vod_id"] == "test_001"
