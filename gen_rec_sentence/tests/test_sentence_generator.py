"""sentence_generator.py 단위 테스트 (Ollama mock)."""

import sys
sys.path.insert(0, ".")

from unittest.mock import patch, MagicMock
from gen_rec_sentence.src.sentence_generator import generate_sentence, _parse_json_response


_CTX = {
    "vod_id": "test_001",
    "asset_nm": "덩케르크",
    "genre": "전쟁",
    "genre_detail": "액션",
    "director": "크리스토퍼 놀란",
    "cast_lead": "킬리언 머피",
    "smry": "2차 세계대전...",
    "rating": "12세",
    "embedding": [0.1] * 512,
}


class TestParseJsonResponse:
    def test_plain_json(self):
        result = _parse_json_response('{"rec_sentence": "멋진 문구"}')
        assert result["rec_sentence"] == "멋진 문구"

    def test_markdown_codeblock(self):
        content = '```json\n{"rec_sentence": "멋진 문구"}\n```'
        result = _parse_json_response(content)
        assert result["rec_sentence"] == "멋진 문구"

    def test_with_prefix_text(self):
        content = '네, 아래와 같이 작성했습니다.\n{"rec_sentence": "멋진 문구"}'
        result = _parse_json_response(content)
        assert result["rec_sentence"] == "멋진 문구"


class TestGenerateSentence:
    def test_success(self):
        mock_response = {"message": {"content": '{"rec_sentence": "총알이 빗발치는 해변.\n하늘을 덮은 적의 그림자."}'}}
        with patch("gen_rec_sentence.src.sentence_generator.ollama") as mock_ollama:
            mock_ollama.chat.return_value = mock_response
            result = generate_sentence(_CTX)
        assert result["vod_id"] == "test_001"
        assert "총알" in result["rec_sentence"]
        assert result["embedding_used"] is True

    def test_json_parse_failure_returns_none(self):
        mock_response = {"message": {"content": "유효하지 않은 응답"}}
        with patch("gen_rec_sentence.src.sentence_generator.ollama") as mock_ollama:
            mock_ollama.chat.return_value = mock_response
            result = generate_sentence(_CTX, max_retries=0)
        assert result["rec_sentence"] is None
        assert "error" in result
