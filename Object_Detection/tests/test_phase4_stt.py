"""
Phase 4 테스트 — Whisper STT 멀티모달
TDD Red 단계: 구현 전 먼저 작성

테스트 대상:
  - src/audio_extractor.py  (AudioExtractor)
  - src/stt_scorer.py       (SttScorer)
  - src/keyword_mapper.py   (KeywordMapper)
"""
import pytest
import sys
import yaml
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

CONFIG_PATH = Path(__file__).parent.parent / "config" / "stt_keywords.yaml"


# ─────────────────────────────────────────
# 픽스처
# ─────────────────────────────────────────

@pytest.fixture(scope="session")
def stt_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def whisper_available():
    try:
        import whisper
        return True
    except ImportError:
        return False


@pytest.fixture(scope="session")
def ffmpeg_available():
    import subprocess
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


# ─────────────────────────────────────────
# P4-01 ~ 03: stt_keywords.yaml 구조 검증
# ─────────────────────────────────────────

def test_P4_01_config_has_required_categories(stt_config):
    """필수 카테고리 존재 여부 확인"""
    required = {"지방특산물", "한식", "과일채소"}
    actual = set(stt_config.keys())
    missing = required - actual
    assert not missing, f"누락된 카테고리: {missing}"


def test_P4_02_keywords_have_ad_hints(stt_config):
    """모든 키워드에 ad_hints 리스트 존재"""
    for category, keywords in stt_config.items():
        for keyword, meta in keywords.items():
            assert "ad_hints" in meta, f"{category}/{keyword}: ad_hints 없음"
            assert isinstance(meta["ad_hints"], list), f"{category}/{keyword}: ad_hints가 리스트가 아님"
            assert len(meta["ad_hints"]) >= 1, f"{category}/{keyword}: ad_hints 비어있음"


def test_P4_03_all_keywords_are_strings(stt_config):
    """모든 키워드가 문자열"""
    for category, keywords in stt_config.items():
        for keyword in keywords:
            assert isinstance(keyword, str), f"{category}: '{keyword}' 가 문자열이 아님"


# ─────────────────────────────────────────
# P4-04 ~ 06: KeywordMapper 테스트
# ─────────────────────────────────────────

def test_P4_04_keyword_mapper_import():
    """keyword_mapper 모듈 import"""
    from keyword_mapper import KeywordMapper
    assert KeywordMapper is not None


def test_P4_05_keyword_match_returns_records():
    """키워드 매칭 → records 반환"""
    from keyword_mapper import KeywordMapper
    km = KeywordMapper(str(CONFIG_PATH))
    records = km.match("영광 굴비가 정말 맛있네요", vod_id="test_vod", start_ts=1.0, end_ts=4.0)
    assert isinstance(records, list)
    assert len(records) >= 1
    assert records[0]["keyword"] == "굴비"
    assert records[0]["ad_category"] == "지방특산물"


def test_P4_06_no_keyword_returns_empty():
    """키워드 없는 텍스트 → 빈 리스트"""
    from keyword_mapper import KeywordMapper
    km = KeywordMapper(str(CONFIG_PATH))
    records = km.match("오늘 날씨가 정말 좋네요", vod_id="test_vod", start_ts=0.0, end_ts=3.0)
    assert records == []


# ─────────────────────────────────────────
# P4-07 ~ 09: SttScorer 테스트
# ─────────────────────────────────────────

def test_P4_07_stt_scorer_import():
    """stt_scorer 모듈 import"""
    from stt_scorer import SttScorer
    assert SttScorer is not None


def test_P4_08_stt_scorer_init(whisper_available):
    """SttScorer 초기화 — whisper 모델 로드"""
    if not whisper_available:
        pytest.skip("openai-whisper 미설치")
    from stt_scorer import SttScorer
    scorer = SttScorer(model_name="tiny")
    assert scorer is not None


def test_P4_09_transcribe_returns_segments(whisper_available, tmp_path):
    """transcribe → segments 리스트 반환 (구조 검증)"""
    if not whisper_available:
        pytest.skip("openai-whisper 미설치")
    from stt_scorer import SttScorer
    scorer = SttScorer(model_name="tiny")
    # 무음 WAV 생성 (실제 오디오 없이 구조만 검증)
    import wave, struct
    wav_path = tmp_path / "silent.wav"
    with wave.open(str(wav_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(struct.pack("<" + "h" * 16000, *([0] * 16000)))  # 1초 무음
    segments = scorer.transcribe(str(wav_path))
    assert isinstance(segments, list)
    for seg in segments:
        assert "start" in seg
        assert "end" in seg
        assert "text" in seg


# ─────────────────────────────────────────
# P4-10 ~ 11: AudioExtractor 테스트
# ─────────────────────────────────────────

def test_P4_10_audio_extractor_import():
    """audio_extractor 모듈 import"""
    from audio_extractor import AudioExtractor
    assert AudioExtractor is not None


def test_P4_11_ffmpeg_available(ffmpeg_available):
    """ffmpeg 실행 가능 여부"""
    assert ffmpeg_available, "ffmpeg가 PATH에 없음"


# ─────────────────────────────────────────
# P4-12: records 스키마 검증
# ─────────────────────────────────────────

def test_P4_12_match_record_schema():
    """매칭 레코드에 필수 컬럼 포함"""
    from keyword_mapper import KeywordMapper
    km = KeywordMapper(str(CONFIG_PATH))
    records = km.match("대게가 맛있다", vod_id="test_vod", start_ts=2.0, end_ts=5.0)
    assert len(records) >= 1
    required_cols = {"vod_id", "start_ts", "end_ts", "transcript", "keyword", "ad_category", "ad_hints", "context_valid", "context_reason"}
    for r in records:
        missing = required_cols - set(r.keys())
        assert not missing, f"누락 컬럼: {missing}"
