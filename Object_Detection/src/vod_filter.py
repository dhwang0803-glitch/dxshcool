"""
vod_filter.py — DB ct_cl 기준 VOD 필터링 유틸리티

public.vod 테이블에서 ct_cl 조건에 맞는 full_asset_id 집합을 반환한다.
"""
from __future__ import annotations
import os
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def load_vod_ids_by_ct_cl(ct_cl: str) -> set[str]:
    """
    DB에서 ct_cl이 일치하는 full_asset_id 집합을 반환한다.
    DB 접속 실패 시 빈 set 반환 (필터 미적용으로 fallback).

    Args:
        ct_cl: 예) "TV 연예/오락"

    Returns:
        {"vod_id_1", "vod_id_2", ...}
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    try:
        import psycopg2
    except ImportError:
        log.warning("psycopg2 미설치 — ct_cl 필터 미적용")
        return set()

    host     = os.getenv("DB_HOST")
    port     = int(os.getenv("DB_PORT", "5432"))
    dbname   = os.getenv("DB_NAME")
    user     = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    if not all([host, dbname, user, password]):
        log.warning("DB 환경변수 미설정 — ct_cl 필터 미적용")
        return set()

    try:
        conn = psycopg2.connect(
            host=host, port=port, dbname=dbname,
            user=user, password=password, connect_timeout=10
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT full_asset_id FROM public.vod WHERE ct_cl = %s",
            (ct_cl,)
        )
        vod_ids = {row[0] for row in cur.fetchall()}
        conn.close()
        log.info(f"ct_cl='{ct_cl}' 필터: {len(vod_ids):,}건 로드")
        return vod_ids
    except Exception as e:
        log.warning(f"DB 조회 실패 — ct_cl 필터 미적용: {e}")
        return set()


def filter_videos_by_ct_cl(video_files: list, ct_cl: str) -> list:
    """
    video_files 중 ct_cl 조건에 맞는 vod_id(파일명 stem)만 반환.
    DB 조회 실패 시 원본 리스트 그대로 반환.

    Args:
        video_files: Path 객체 리스트
        ct_cl: 예) "TV 연예/오락"

    Returns:
        필터링된 Path 리스트
    """
    vod_ids = load_vod_ids_by_ct_cl(ct_cl)
    if not vod_ids:
        return video_files

    def extract_asset_id(path) -> str:
        """
        cjc#M0130664LSGJ24872601__20kaO225J20 → cjc|M0130664LSGJ24872601
        파일명의 # → DB의 | 로 변환, __ 이후 YouTube ID 제거
        """
        stem = path.stem
        asset_id = stem.split("__")[0] if "__" in stem else stem
        return asset_id.replace("#", "|")

    filtered = [f for f in video_files if extract_asset_id(f) in vod_ids]
    log.info(f"ct_cl 필터 적용: {len(video_files):,} → {len(filtered):,}건")
    return filtered
