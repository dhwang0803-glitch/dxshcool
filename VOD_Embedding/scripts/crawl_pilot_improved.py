"""
크롤링 개선 파일럿 테스트 스크립트

기존 crawl_trailers.py 대비 개선 사항 검증:
  1. release_date 기반 방송일 포함 쿼리 (TV 연예/오락 에피소드별 검색)
  2. 제목 띄어쓰기 가설 검증 — konlpy Okt 사전 실험 결과, 과분할 문제로 미채택
     '겨울왕국' → Okt 단일 토큰 인식 (이미 정상), 제목 표기 이슈는 별도 원인
  3. 영화: 낱말 순서 변형 쿼리 추가 (old/foreign title fallback)

실행:
    # 쿼리 비교만 (실제 다운로드 없음)
    python scripts/crawl_pilot_improved.py --dry-run --limit 30

    # 실제 파일럿 크롤 (성공/실패율 측정)
    python scripts/crawl_pilot_improved.py --limit 20 --trailers-dir ./data/pilot_trailers
"""

import os
import re
import sys
import json
import time
import random
import argparse
import logging
from datetime import datetime, date
from pathlib import Path
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv()

sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# -------------------------------------------------------------------
# 설정
# -------------------------------------------------------------------

REQUEST_DELAY_MIN = 1.5
REQUEST_DELAY_MAX = 3.0
DURATION_MIN_SEC  = 30
DURATION_MAX_SEC  = 300
MAX_FILESIZE_BYTES = 50 * 1024 * 1024

# 파일럿 ct_cl별 샘플 수
PILOT_SAMPLE_PLAN = {
    "TV 연예/오락": 10,   # 방송일 쿼리 개선 검증 핵심
    "영화":          8,   # 제목 표기 문제 검증
    "TV드라마":       7,
    "TV애니메이션":   5,
}

SERIES_CT_CL = {"TV드라마", "TV 시사/교양", "TV애니메이션", "키즈", "영화"}


# -------------------------------------------------------------------
# DB 연결
# -------------------------------------------------------------------

def get_db_conn():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


# -------------------------------------------------------------------
# VOD 조회 — release_date 포함 (기존 대비 개선)
# -------------------------------------------------------------------

def fetch_vod_sample(total: int = 30) -> list:
    """
    ct_cl 계층별 샘플 조회.
    기존 crawl_trailers.py fetch_vod_list 대비: release_date 컬럼 추가.
    """
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        result = []
        for ct_cl, quota in PILOT_SAMPLE_PLAN.items():
            cur.execute(
                """
                SELECT full_asset_id, asset_nm, ct_cl, genre, series_nm, release_date
                FROM vod
                WHERE ct_cl = %s
                ORDER BY full_asset_id
                LIMIT %s
                """,
                (ct_cl, quota * 10),  # dedup 여유분
            )
            rows = cur.fetchall()
            vods = [
                {
                    "vod_id":       r[0],
                    "asset_nm":     r[1],
                    "ct_cl":        r[2],
                    "genre":        r[3],
                    "series_nm":    r[4],
                    "release_date": r[5],
                }
                for r in rows
            ]
            # 시리즈 단위 ct_cl은 series_nm 기준 dedup
            if ct_cl in SERIES_CT_CL:
                seen, deduped = set(), []
                for v in vods:
                    key = (v["series_nm"] or v["asset_nm"]).strip()
                    if key not in seen:
                        seen.add(key)
                        deduped.append(v)
                vods = deduped
            result.extend(vods[:quota])
        log.info(f"샘플 로드 완료: {len(result)}건")
        return result
    finally:
        conn.close()


# -------------------------------------------------------------------
# 제목 정규화
# -------------------------------------------------------------------

def normalize_title(name: str) -> str:
    """
    숫자↔한글 경계 공백 삽입.
    ※ konlpy Okt 사전 실험 결과 제목 과분할 문제로 미채택:
       '겨울왕국' → 단일 토큰(정상), '1724기방난동사건' → '1724 기 방 난 동 사건'(비정상)
    """
    name = re.sub(r"(\d)([가-힣])", r"\1 \2", name)
    name = re.sub(r"([가-힣])(\d)", r"\1 \2", name)
    return name.strip()


def strip_episode_suffix(name: str) -> str:
    """에피소드 번호 제거 → 시리즈명 추출."""
    name = re.sub(r"\s*\d+\s*[회화]\.?$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+ep\.?\s*\d+$", "", name, flags=re.IGNORECASE)
    return name.strip()


# -------------------------------------------------------------------
# 쿼리 빌드 — 기존 버전 (비교 기준)
# -------------------------------------------------------------------

def build_queries_original(asset_nm: str, ct_cl: str, series_nm: str = None) -> list:
    """기존 crawl_trailers.py build_search_queries와 동일 로직."""
    name   = asset_nm.strip()
    norm   = normalize_title(name)
    series = strip_episode_suffix(name)
    movie_nm = normalize_title(series_nm.strip()) if series_nm else norm

    if ct_cl == "영화":
        return [
            f"{movie_nm} 예고편",
            f"{movie_nm} official trailer",
            f"{movie_nm} 공식 예고편",
            f"{movie_nm} trailer",
        ]
    elif ct_cl in ("TV드라마", "TV 연예/오락", "TV 시사/교양"):
        return [
            f"{series} 예고편",
            f"{series} 하이라이트",
            f"{series} 1회",
            f"{series} trailer",
        ]
    elif ct_cl == "TV애니메이션":
        return [f"{series} 예고편", f"{series} trailer", f"{series} PV"]
    else:
        return [f"{name} 예고편", f"{name} trailer"]


# -------------------------------------------------------------------
# 쿼리 빌드 — 개선 버전
# -------------------------------------------------------------------

def _date_str(release_date) -> str | None:
    """
    release_date → YYMMDD 문자열 변환.
    YouTube 방송 영상 제목 형식 예: '[예고] 슈퍼맨이 돌아왔다 KBS 260318'
    """
    if release_date is None:
        return None
    if isinstance(release_date, date):
        return release_date.strftime("%y%m%d")
    try:
        from datetime import datetime as dt
        return dt.strptime(str(release_date)[:10], "%Y-%m-%d").strftime("%y%m%d")
    except Exception:
        return None


def build_queries_improved(
    asset_nm: str,
    ct_cl: str,
    series_nm: str = None,
    release_date=None,
) -> list:
    """
    개선된 쿼리 빌더.

    변경점:
      1. TV 연예/오락: release_date YYMMDD 포함 쿼리 우선 배치
      2. 영화: 낱제목(예고편 없이) + 연도 기반 fallback 쿼리 추가
      3. 기존 쿼리는 fallback으로 유지 (하위 호환)
    """
    name     = asset_nm.strip()
    norm     = normalize_title(name)
    series   = strip_episode_suffix(name)
    movie_nm = normalize_title(series_nm.strip()) if series_nm else norm
    date_s   = _date_str(release_date)

    if ct_cl == "영화":
        queries = [
            f"{movie_nm} 예고편",
            f"{movie_nm} official trailer",
            f"{movie_nm} 공식 예고편",
        ]
        # 개선: 연도 기반 fallback (구작 포스터 영상 대응)
        if release_date:
            year = str(release_date.year if isinstance(release_date, date) else release_date)[:4]
            queries.append(f"{movie_nm} {year}")
        queries.append(f"{movie_nm} trailer")
        return queries

    elif ct_cl in ("TV드라마", "TV 시사/교양"):
        return [
            f"{series} 예고편",
            f"{series} 하이라이트",
            f"{series} 1회",
            f"{series} trailer",
        ]

    elif ct_cl == "TV 연예/오락":
        queries = []
        # 개선: 방송일 포함 쿼리를 최우선 배치
        if date_s:
            queries.append(f"{series} {date_s}")            # '슈퍼맨이 돌아왔다 260318'
            queries.append(f"{series} {date_s} 예고")       # '[예고]' 태그 매칭
        # 기존 쿼리 fallback
        queries.extend([
            f"{series} 예고편",
            f"{series} 하이라이트",
            f"{series} 1회",
            f"{series} trailer",
        ])
        return queries

    elif ct_cl == "TV애니메이션":
        return [f"{series} 예고편", f"{series} trailer", f"{series} PV"]

    else:
        return [f"{name} 예고편", f"{name} trailer"]


# -------------------------------------------------------------------
# 실제 다운로드 시도
# -------------------------------------------------------------------

def duration_filter(info, incomplete):
    if incomplete:
        return None
    duration = info.get("duration") or 0
    if duration < DURATION_MIN_SEC:
        return f"너무 짧음 ({duration}초)"
    if duration > DURATION_MAX_SEC:
        return f"너무 김 ({duration}초)"
    return None


def try_search(vod_id: str, queries: list) -> dict:
    """
    다운로드 없이 YouTube 검색 결과만 확인.
    첫 번째로 결과가 나오는 쿼리와 영상 제목을 반환한다.
    """
    try:
        import yt_dlp
    except ImportError:
        return {"status": "error", "reason": "yt_dlp_not_installed"}

    for query in queries:
        time.sleep(random.uniform(0.5, 1.5))
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,   # 메타데이터만 조회 (다운로드 없음)
            "socket_timeout": 15,
            "noplaylist": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                if info and info.get("entries") and len(info["entries"]) > 0:
                    entry = info["entries"][0]
                    return {
                        "status": "hit",
                        "query_used": query,
                        "video_title": entry.get("title", ""),
                        "duration_sec": entry.get("duration", 0),
                        "video_id": entry.get("id", ""),
                    }
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "Too Many Requests" in err_str:
                log.warning("YouTube 429 — 60초 대기")
                time.sleep(60)
            log.debug(f"{vod_id} 쿼리 실패 '{query}': {e}")
            continue

    return {"status": "miss", "tried_queries": queries}


def try_download(vod_id: str, queries: list, output_dir: Path, dry_run: bool) -> dict:
    if dry_run:
        return {
            "status": "dry_run",
            "query_used": queries[0] if queries else "",
        }

    try:
        import yt_dlp
    except ImportError:
        return {"status": "error", "reason": "yt_dlp_not_installed"}

    output_dir.mkdir(parents=True, exist_ok=True)

    for query in queries:
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))
        ydl_opts = {
            "format": "worst[ext=webm]/worst",
            "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "match_filter": duration_filter,
            "max_filesize": MAX_FILESIZE_BYTES,
            "retries": 2,
            "socket_timeout": 30,
            "default_search": "ytsearch1",
            "noplaylist": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch1:{query}", download=True)
                if info and info.get("entries"):
                    entry = info["entries"][0]
                    return {
                        "status": "success",
                        "filename": f"{entry['id']}.{entry.get('ext','webm')}",
                        "query_used": query,
                        "duration_sec": entry.get("duration", 0),
                    }
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "Too Many Requests" in err_str:
                log.warning("YouTube 429 — 60초 대기")
                time.sleep(60)
            log.debug(f"{vod_id} 쿼리 실패 '{query}': {e}")
            continue

    return {"status": "failed", "reason": "no_result", "tried_queries": queries}


# -------------------------------------------------------------------
# 파이럿 실행
# -------------------------------------------------------------------

def run_pilot(limit: int, trailers_dir: Path, dry_run: bool, search_only: bool = False):
    log.info("=== 크롤링 개선 파일럿 시작 ===")
    log.info(f"  dry_run={dry_run}, search_only={search_only}, limit={limit}")

    vods = fetch_vod_sample(total=limit)[:limit]

    # 쿼리 비교 출력
    log.info("\n[쿼리 비교: 기존 vs 개선]")
    log.info(f"{'제목':<30} {'ct_cl':<14} {'release_date':<14} {'기존 첫번째 쿼리':<40} 개선 첫번째 쿼리")
    log.info("-" * 140)
    for v in vods:
        old_q = build_queries_original(v["asset_nm"], v["ct_cl"], v["series_nm"])
        new_q = build_queries_improved(v["asset_nm"], v["ct_cl"], v["series_nm"], v["release_date"])
        changed = "✅" if old_q[0] != new_q[0] else "  "
        title_short = v["asset_nm"][:28]
        rd = str(v["release_date"]) if v["release_date"] else "없음"
        log.info(f"{changed} {title_short:<30} {v['ct_cl']:<14} {rd:<14} {old_q[0]:<40} {new_q[0]}")

    if dry_run:
        # 쿼리 변경 통계
        changed = sum(
            1 for v in vods
            if build_queries_original(v["asset_nm"], v["ct_cl"], v["series_nm"])[0]
            != build_queries_improved(v["asset_nm"], v["ct_cl"], v["series_nm"], v["release_date"])[0]
        )
        has_date = sum(1 for v in vods if v["ct_cl"] == "TV 연예/오락" and v["release_date"])
        no_date  = sum(1 for v in vods if v["ct_cl"] == "TV 연예/오락" and not v["release_date"])
        log.info(f"\n[dry-run 통계]")
        log.info(f"  전체 샘플: {len(vods)}건")
        log.info(f"  쿼리 변경: {changed}건 ({changed/len(vods)*100:.1f}%)")
        log.info(f"  TV 연예/오락 release_date 있음: {has_date}건 → 방송일 쿼리 적용 가능")
        log.info(f"  TV 연예/오락 release_date 없음: {no_date}건 → 기존 쿼리 유지")
        return

    if search_only:
        # YouTube 검색 히트 여부만 확인 (다운로드 없음)
        log.info("\n[검색 히트 테스트 — 다운로드 없음]")
        stats = {"original": {"hit": 0, "miss": 0}, "improved": {"hit": 0, "miss": 0}}

        for v in vods:
            vod_id = v["vod_id"]
            old_qs = build_queries_original(v["asset_nm"], v["ct_cl"], v["series_nm"])
            new_qs = build_queries_improved(v["asset_nm"], v["ct_cl"], v["series_nm"], v["release_date"])

            old_r = try_search(vod_id, old_qs)
            new_r = try_search(vod_id, new_qs)

            old_hit = old_r["status"] == "hit"
            new_hit = new_r["status"] == "hit"
            stats["original"]["hit" if old_hit else "miss"] += 1
            stats["improved"]["hit" if new_hit else "miss"] += 1

            # 기존/개선 결과 비교 표시
            diff = ""
            if not old_hit and new_hit:
                diff = " ← 개선 효과"
            elif old_hit and not new_hit:
                diff = " ← 개선 후 실패(주의)"

            old_title = old_r.get("video_title", "")[:35]
            new_title = new_r.get("video_title", "")[:35]
            log.info(
                f"\n  [{v['asset_nm'][:25]}] ({v['ct_cl']}){diff}\n"
                f"    기존({'HIT' if old_hit else 'MISS'}): {old_qs[0][:35]}\n"
                f"         → {old_title}\n"
                f"    개선({'HIT' if new_hit else 'MISS'}): {new_qs[0][:35]}\n"
                f"         → {new_title}"
            )

        total = len(vods)
        log.info("\n=== 검색 히트 결과 ===")
        for label, stat in stats.items():
            h, m = stat["hit"], stat["miss"]
            log.info(f"  [{label}] HIT: {h}/{total} ({h/total*100:.1f}%)  MISS: {m}/{total}")
        improvement = stats["improved"]["hit"] - stats["original"]["hit"]
        log.info(f"  개선 효과: +{improvement}건 HIT 증가")
        return

    # 실제 크롤
    results = {"original": {"success": 0, "failed": 0}, "improved": {"success": 0, "failed": 0}}

    for v in vods:
        vod_id   = v["vod_id"]
        old_qs   = build_queries_original(v["asset_nm"], v["ct_cl"], v["series_nm"])
        new_qs   = build_queries_improved(v["asset_nm"], v["ct_cl"], v["series_nm"], v["release_date"])

        # 기존 쿼리로 시도
        old_result = try_download(vod_id + "_old", old_qs, trailers_dir / "original", dry_run)
        results["original"]["success" if old_result["status"] == "success" else "failed"] += 1

        # 개선 쿼리로 시도
        new_result = try_download(vod_id + "_new", new_qs, trailers_dir / "improved", dry_run)
        results["improved"]["success" if new_result["status"] == "success" else "failed"] += 1

        log.info(
            f"{v['asset_nm'][:25]:<25} | "
            f"기존: {'OK' if old_result['status']=='success' else 'FAIL'} ({old_qs[0][:30]}) | "
            f"개선: {'OK' if new_result['status']=='success' else 'FAIL'} ({new_qs[0][:30]})"
        )

    # 결과 리포트
    total = len(vods)
    log.info("\n=== 파이럿 결과 ===")
    for label, stat in results.items():
        s, f = stat["success"], stat["failed"]
        log.info(f"  [{label}] 성공: {s}/{total} ({s/total*100:.1f}%)  실패: {f}/{total} ({f/total*100:.1f}%)")

    improvement = results["improved"]["success"] - results["original"]["success"]
    log.info(f"  개선 효과: +{improvement}건 성공 증가")


# -------------------------------------------------------------------
# 진입점
# -------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="크롤링 개선 파일럿")
    parser.add_argument("--dry-run", action="store_true", help="쿼리 비교만 출력 (다운로드 없음)")
    parser.add_argument("--search-only", action="store_true", help="YouTube 검색 히트 여부만 확인 (다운로드 없음)")
    parser.add_argument("--limit", type=int, default=30, help="샘플 건수 (기본 30)")
    parser.add_argument("--trailers-dir", type=str, default="./data/pilot_trailers",
                        help="트레일러 저장 경로")
    args = parser.parse_args()

    run_pilot(
        limit=args.limit,
        trailers_dir=Path(args.trailers_dir),
        dry_run=args.dry_run,
        search_only=args.search_only,
    )


if __name__ == "__main__":
    main()
