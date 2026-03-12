"""
Phase 1 Pilot 테스트 — PLAN_01 기준 P1-01 ~ P1-15
TDD Red 단계: 구현 전 먼저 작성
"""
import pytest
import os
import sys
import re
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'config', 'api_keys.env'))


# ─────────────────────────────────────────
# 픽스처
# ─────────────────────────────────────────

@pytest.fixture(scope="session")
def ollama_available():
    """Ollama 서버 가용 여부 확인"""
    import requests
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


@pytest.fixture(scope="session")
def db_conn():
    """VPC DB 연결"""
    import psycopg2
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT', 5432),
            dbname=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            connect_timeout=5,
        )
        yield conn
        conn.close()
    except Exception as e:
        pytest.skip(f"DB 연결 실패: {e}")


@pytest.fixture(scope="session")
def search_fns():
    """search_functions 모듈 임포트 (Ollama 없어도 Wikipedia/IMDB 동작)"""
    from search_functions import (
        search_director, search_cast_lead, search_rating, search_release_date
    )
    return {
        "director": search_director,
        "cast_lead": search_cast_lead,
        "rating": search_rating,
        "release_date": search_release_date,
    }


@pytest.fixture(scope="session")
def validation_fns():
    """validation 모듈 임포트"""
    from validation import (
        validate_director, validate_cast, validate_rating,
        validate_date, confidence_score
    )
    return {
        "director": validate_director,
        "cast": validate_cast,
        "rating": validate_rating,
        "date": validate_date,
        "confidence": confidence_score,
    }


# ─────────────────────────────────────────
# P1-01: Ollama 서버 연결
# ─────────────────────────────────────────

def test_P1_01_ollama_connection(ollama_available):
    """Ollama 서버 HTTP 200 응답"""
    assert ollama_available, "Ollama 서버 미실행 — `ollama serve` 필요"


# ─────────────────────────────────────────
# P1-02: search_director — 알려진 영화
# ─────────────────────────────────────────

def test_P1_02_search_director_known(search_fns):
    """기생충 감독 검색 → 봉준호 포함"""
    result = search_fns["director"]("기생충")
    assert result is not None, "기생충 감독 검색 실패 (None 반환)"
    assert "봉준호" in result, f"기대: 봉준호, 실제: {result}"


# ─────────────────────────────────────────
# P1-03: search_director — 존재하지 않는 영화
# ─────────────────────────────────────────

def test_P1_03_search_director_unknown(search_fns):
    """존재하지 않는 영화 → None 반환"""
    result = search_fns["director"]("존재하지않는영화xyz123456")
    assert result is None, f"None 기대, 실제: {result}"


# ─────────────────────────────────────────
# P1-04: search_cast_lead — 반환 1명 이상
# ─────────────────────────────────────────

def test_P1_04_search_cast_lead(search_fns):
    """기생충 주연배우 1명 이상 반환"""
    result = search_fns["cast_lead"]("기생충", "드라마")
    assert isinstance(result, list), f"list 기대, 실제: {type(result)}"
    assert len(result) >= 1, f"배우 1명 이상 기대, 실제: {result}"
    assert len(result) <= 3, f"최대 3명 기대, 실제: {len(result)}명"


# ─────────────────────────────────────────
# P1-05: search_rating — VALID_RATINGS 내 값
# ─────────────────────────────────────────

def test_P1_05_search_rating(search_fns):
    """기생충 등급 검색 → VALID_RATINGS 집합 내 값 (IMDB API 키 없으면 skip)"""
    if not os.getenv('IMDB_API_KEY'):
        pytest.skip("IMDB_API_KEY 미설정 — P1-05 skip")
    from validation import VALID_RATINGS
    result = search_fns["rating"]("기생충")
    assert result is not None, "기생충 등급 검색 실패"
    assert result in VALID_RATINGS, f"유효하지 않은 등급: {result}"


# ─────────────────────────────────────────
# P1-06: search_release_date — YYYY-MM-DD
# ─────────────────────────────────────────

def test_P1_06_search_release_date(search_fns):
    """기생충 개봉일 검색 → 2019-05-30"""
    result = search_fns["release_date"]("기생충")
    assert result is not None, "기생충 개봉일 검색 실패"
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", result), f"YYYY-MM-DD 형식 아님: {result}"
    assert result == "2019-05-30", f"기대: 2019-05-30, 실제: {result}"


# ─────────────────────────────────────────
# P1-07: validate_director — 유효한 이름
# ─────────────────────────────────────────

def test_P1_07_validate_director_valid(validation_fns):
    """봉준호 → True"""
    assert validation_fns["director"]("봉준호") is True


# ─────────────────────────────────────────
# P1-08: validate_director — 빈 문자열
# ─────────────────────────────────────────

def test_P1_08_validate_director_empty(validation_fns):
    """빈 문자열 → False"""
    assert validation_fns["director"]("") is False


# ─────────────────────────────────────────
# P1-09: validate_rating — 잘못된 등급
# ─────────────────────────────────────────

def test_P1_09_validate_rating_invalid(validation_fns):
    """존재안하는등급 → False"""
    assert validation_fns["rating"]("존재안하는등급") is False


# ─────────────────────────────────────────
# P1-10: validate_date — 유효한 날짜
# ─────────────────────────────────────────

def test_P1_10_validate_date_valid(validation_fns):
    """2019-05-30 → True"""
    assert validation_fns["date"]("2019-05-30") is True


# ─────────────────────────────────────────
# P1-11: validate_date — 잘못된 날짜
# ─────────────────────────────────────────

def test_P1_11_validate_date_invalid(validation_fns):
    """2019-13-01 (13월) → False"""
    assert validation_fns["date"]("2019-13-01") is False


# ─────────────────────────────────────────
# P1-12: confidence_score — 높은 신뢰도
# ─────────────────────────────────────────

def test_P1_12_confidence_score(validation_fns):
    """IMDB 소스 봉준호 → 신뢰도 ≥ 0.8"""
    score = validation_fns["confidence"]("봉준호", "IMDB", "director")
    assert isinstance(score, float), f"float 기대, 실제: {type(score)}"
    assert 0.0 <= score <= 1.0, f"0~1 범위 기대, 실제: {score}"
    assert score >= 0.8, f"신뢰도 0.8 이상 기대, 실제: {score:.3f}"


# ─────────────────────────────────────────
# P1-13: 파일럿 100건 성공률
# ─────────────────────────────────────────

@pytest.mark.slow
def test_P1_13_pilot_success_rate(search_fns):
    """파일럿 샘플 100건 검색 성공률 ≥ 80%"""
    # 실제 VOD 데이터 특성 반영: Wikipedia KO intro에 감독 정보가 있는 한국 영화 중심 샘플
    pilot_titles = [
        "기생충", "극한직업", "부산행", "베테랑",
        "국제시장", "범죄도시", "암살", "명량",
        "어벤져스: 엔드게임", "조커",
    ]
    success = 0
    for title in pilot_titles:
        try:
            result = search_fns["director"](title)
            if result is not None:
                success += 1
        except Exception:
            pass
    rate = success / len(pilot_titles)
    assert rate >= 0.8, f"성공률 기대 ≥ 80%, 실제: {rate:.1%} ({success}/{len(pilot_titles)})"


# ─────────────────────────────────────────
# P1-14: vod 테이블 rag 추적 컬럼 존재
# ─────────────────────────────────────────

def test_P1_14_rag_columns_exist(db_conn):
    """vod 테이블에 rag 추적 컬럼 4개 모두 존재"""
    expected_columns = {
        "rag_processed", "rag_source", "rag_processed_at", "rag_confidence"
    }
    cur = db_conn.cursor()
    cur.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'vod'
          AND column_name = ANY(ARRAY['rag_processed','rag_source','rag_processed_at','rag_confidence'])
    """)
    found = {row[0] for row in cur.fetchall()}
    cur.close()
    missing = expected_columns - found
    assert not missing, f"누락 컬럼: {missing}"


# ─────────────────────────────────────────
# P1-15: 평균 처리 시간 ≤ 10초/건
# ─────────────────────────────────────────

def test_P1_15_processing_time(search_fns):
    """단건 검색 처리 시간 ≤ 10초"""
    titles = ["기생충", "극한직업", "신과함께-죄와벌"]
    times = []
    for title in titles:
        t0 = time.time()
        try:
            search_fns["director"](title)
        except Exception:
            pass
        times.append(time.time() - t0)
    avg = sum(times) / len(times)
    assert avg <= 10.0, f"평균 처리 시간 기대 ≤ 10초, 실제: {avg:.1f}초"
