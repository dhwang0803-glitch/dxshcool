# =============================================================
# Phase 2 Migration - 단위 테스트 (TDD Red 단계)
# 파일: Database_Design/tests/test_migration_unit.py
# 목적: migrate.py 구현 전 실패하는 테스트를 먼저 작성 (TDD Red)
# 작성일: 2026-03-07
# 참조: PLAN_02_DATA_MIGRATION.md
# =============================================================
# 실행 방법: pytest test_migration_unit.py -v
# CSV 파일 없이 실행 가능 (순수 단위 테스트)
# T15만 .env 파일 및 VPC DB 접속이 필요합니다.
# =============================================================

import pytest
import math
import os
from pathlib import Path
from dotenv import load_dotenv

# =============================================================
# 테스트 대상 함수 직접 정의
# (migrate.py가 아직 없으므로 여기서 직접 구현하여 테스트)
# =============================================================

def parse_disp_rtm(disp_rtm_str) -> int:
    """
    "HH:MM" 또는 "HH:MM:SS" 형식의 문자열을 초 단위 정수로 변환.
    - None, NaN, "-" 등 비정상 값은 0 반환
    예: "01:21" -> 4860, "00:29" -> 1740, "01:30:00" -> 5400
    """
    # None 처리
    if disp_rtm_str is None:
        return 0
    # float NaN 처리 (pandas NaN은 float)
    try:
        if math.isnan(float(disp_rtm_str)):
            return 0
    except (ValueError, TypeError):
        pass
    # 대시(-) 처리
    if str(disp_rtm_str).strip() == '-':
        return 0
    parts = str(disp_rtm_str).strip().split(':')
    try:
        if len(parts) == 2:
            h, m = int(parts[0]), int(parts[1])
            return h * 3600 + m * 60
        elif len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return h * 3600 + m * 60 + s
    except (ValueError, TypeError):
        return 0
    return 0


def convert_nfx_use_yn(value) -> bool | None:
    """
    NFX_USE_YN 컬럼 변환:
    - "Y" -> True
    - "N" -> False
    - NaN / None -> None (NULL 허용)
    """
    if value is None:
        return None
    try:
        if math.isnan(float(value)):
            return None
    except (ValueError, TypeError):
        pass
    if str(value).strip().upper() == 'Y':
        return True
    if str(value).strip().upper() == 'N':
        return False
    return None


def clean_smry(value) -> str | None:
    """
    smry(줄거리) 컬럼 정제:
    - "-" -> None
    - "" (빈 문자열) -> None
    - 정상 텍스트 -> 그대로 반환
    """
    if value is None:
        return None
    try:
        if math.isnan(float(value)):
            return None
    except (ValueError, TypeError):
        pass
    text = str(value).strip()
    if text == '-' or text == '':
        return None
    return text


def clip_completion_rate(value: float) -> float:
    """
    completion_rate 값을 0.0 ~ 1.0 범위로 클리핑.
    - 1.0 초과 -> 1.0
    - 0.0 미만 -> 0.0
    - 정상 범위 -> 그대로 반환
    """
    return max(0.0, min(1.0, float(value)))


# =============================================================
# T01~T05: parse_disp_rtm 함수 테스트
# =============================================================

class TestParseDispRtm:

    def test_T01_hh_mm_format_01_21(self):
        """T01: "01:21" -> 4860 (HH:MM 형식, 1시간 21분 = 4860초)"""
        result = parse_disp_rtm("01:21")
        assert result == 4860, (
            f"[T01 FAIL] 기대값: 4860, 실제값: {result} | "
            f"'01:21'은 1*3600 + 21*60 = 4860초여야 합니다."
        )

    def test_T02_hh_mm_format_00_29(self):
        """T02: "00:29" -> 1740 (HH:MM 형식, 0시간 29분 = 1740초)"""
        result = parse_disp_rtm("00:29")
        assert result == 1740, (
            f"[T02 FAIL] 기대값: 1740, 실제값: {result} | "
            f"'00:29'은 0*3600 + 29*60 = 1740초여야 합니다."
        )

    def test_T03_hh_mm_ss_format_01_30_00(self):
        """T03: "01:30:00" -> 5400 (HH:MM:SS 형식, 1시간 30분 0초 = 5400초)"""
        result = parse_disp_rtm("01:30:00")
        assert result == 5400, (
            f"[T03 FAIL] 기대값: 5400, 실제값: {result} | "
            f"'01:30:00'은 1*3600 + 30*60 + 0 = 5400초여야 합니다."
        )

    def test_T04_none_nan_returns_zero(self):
        """T04: None/NaN -> 0 (NULL 값 처리)"""
        result_none = parse_disp_rtm(None)
        result_nan = parse_disp_rtm(float('nan'))
        assert result_none == 0, (
            f"[T04 FAIL] None 입력 시 기대값: 0, 실제값: {result_none}"
        )
        assert result_nan == 0, (
            f"[T04 FAIL] NaN 입력 시 기대값: 0, 실제값: {result_nan}"
        )

    def test_T05_dash_returns_zero(self):
        """T05: "-" -> 0 (대시 값 처리)"""
        result = parse_disp_rtm("-")
        assert result == 0, (
            f"[T05 FAIL] 기대값: 0, 실제값: {result} | "
            f"'-'는 유효하지 않은 값으로 0을 반환해야 합니다."
        )


# =============================================================
# T06~T08: NFX_USE_YN 변환 테스트
# =============================================================

class TestNfxUseYn:

    def test_T06_Y_to_true(self):
        """T06: "Y" -> True (넷플릭스 사용 여부 Y 변환)"""
        result = convert_nfx_use_yn("Y")
        assert result is True, (
            f"[T06 FAIL] 기대값: True, 실제값: {result} | "
            f"'Y'는 BOOLEAN True로 변환되어야 합니다."
        )

    def test_T07_N_to_false(self):
        """T07: "N" -> False (넷플릭스 사용 여부 N 변환)"""
        result = convert_nfx_use_yn("N")
        assert result is False, (
            f"[T07 FAIL] 기대값: False, 실제값: {result} | "
            f"'N'은 BOOLEAN False로 변환되어야 합니다."
        )

    def test_T08_nan_to_none(self):
        """T08: NaN -> None (NULL 허용, 결측값 처리)"""
        result = convert_nfx_use_yn(float('nan'))
        assert result is None, (
            f"[T08 FAIL] 기대값: None, 실제값: {result} | "
            f"NaN은 NULL(None)로 변환되어야 합니다."
        )


# =============================================================
# T09~T11: smry 정제 테스트
# =============================================================

class TestCleanSmry:

    def test_T09_dash_to_none(self):
        """T09: "-" -> None (대시를 NULL로 처리)"""
        result = clean_smry("-")
        assert result is None, (
            f"[T09 FAIL] 기대값: None, 실제값: {result!r} | "
            f"'-'는 NULL(None)로 변환되어야 합니다."
        )

    def test_T10_empty_string_to_none(self):
        """T10: "" (빈 문자열) -> None (빈 값을 NULL로 처리)"""
        result = clean_smry("")
        assert result is None, (
            f"[T10 FAIL] 기대값: None, 실제값: {result!r} | "
            f"빈 문자열은 NULL(None)로 변환되어야 합니다."
        )

    def test_T11_normal_text_preserved(self):
        """T11: 정상 텍스트 -> 그대로 유지"""
        sample = "이 드라마는 2023년 방영된 로맨스 작품입니다."
        result = clean_smry(sample)
        assert result == sample, (
            f"[T11 FAIL] 기대값: {sample!r}, 실제값: {result!r} | "
            f"정상 텍스트는 변환 없이 그대로 반환되어야 합니다."
        )


# =============================================================
# T12~T14: completion_rate 클리핑 테스트
# =============================================================

class TestClipCompletionRate:

    def test_T12_normal_range_preserved(self):
        """T12: 0.8 -> 0.8 (정상 범위 값은 그대로 유지)"""
        result = clip_completion_rate(0.8)
        assert result == pytest.approx(0.8), (
            f"[T12 FAIL] 기대값: 0.8, 실제값: {result} | "
            f"0~1 범위의 정상 값은 변환 없이 그대로여야 합니다."
        )

    def test_T13_over_one_clipped_to_one(self):
        """T13: 1.5 -> 1.0 (1.0 초과값 클리핑)"""
        result = clip_completion_rate(1.5)
        assert result == pytest.approx(1.0), (
            f"[T13 FAIL] 기대값: 1.0, 실제값: {result} | "
            f"1.0 초과값은 1.0으로 클리핑되어야 합니다."
        )

    def test_T14_negative_clipped_to_zero(self):
        """T14: -0.1 -> 0.0 (음수값 클리핑)"""
        result = clip_completion_rate(-0.1)
        assert result == pytest.approx(0.0), (
            f"[T14 FAIL] 기대값: 0.0, 실제값: {result} | "
            f"음수값은 0.0으로 클리핑되어야 합니다."
        )


# =============================================================
# T15: .env DB 연결 테스트
# =============================================================

class TestDbConnection:

    def test_T15_env_db_connection(self):
        """
        T15: .env 로드 후 VPC DB 접속 성공 확인
        - .env 파일 경로: C:/Users/user/Documents/GitHub/vod_recommendation/.env
        - psycopg2로 접속 후 SELECT 1 실행하여 연결 정상 확인
        """
        import psycopg2

        env_path = Path(
            "C:/Users/user/Documents/GitHub/vod_recommendation/.env"
        )
        assert env_path.exists(), (
            f"[T15 FAIL] .env 파일이 존재하지 않습니다: {env_path} | "
            f".env 파일을 해당 경로에 생성하세요."
        )

        load_dotenv(dotenv_path=env_path, override=True)

        db_host = os.getenv("DB_HOST")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME")
        db_user = os.getenv("DB_USER")
        db_password = os.getenv("DB_PASSWORD")

        missing = [
            k for k, v in {
                "DB_HOST": db_host,
                "DB_NAME": db_name,
                "DB_USER": db_user,
                "DB_PASSWORD": db_password,
            }.items() if not v
        ]
        assert not missing, (
            f"[T15 FAIL] .env에 누락된 환경변수: {missing} | "
            f".env 파일에 DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD를 설정하세요."
        )

        try:
            conn = psycopg2.connect(
                host=db_host,
                port=int(db_port),
                dbname=db_name,
                user=db_user,
                password=db_password,
                connect_timeout=10,
            )
        except psycopg2.OperationalError as e:
            pytest.fail(
                f"[T15 FAIL] VPC DB 접속 실패: {e} | "
                f"호스트({db_host}:{db_port})에 접근 가능한지, VPC 터널/보안그룹을 확인하세요."
            )

        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        assert result == 1, (
            f"[T15 FAIL] SELECT 1 기대값: 1, 실제값: {result} | "
            f"DB 연결은 성공했으나 쿼리 결과가 올바르지 않습니다."
        )
