"""
RAG/scripts/fill_missing_episodes.py
=====================================
TMDB에서 DB에 없는 에피소드를 public.vod에 INSERT.

대상 ct_cl:
  TV드라마, TV애니메이션, 키즈, TV시사/교양  (TV 연예/오락 제외)

동작 흐름:
  1. DB에서 시리즈별 에피소드 현황 조회 (existing episode numbers)
  2. TMDB에서 시리즈 검색 → 전체 시즌·에피소드 목록 조회
  3. DB 없는 에피소드 계산 (누적 회차 번호 기준 비교)
  4. INSERT — synthetic full_asset_id, 기존 시리즈 메타데이터 복사
     ON CONFLICT DO NOTHING (중복 안전)

병렬 처리:
  ThreadPoolExecutor(max_workers=N, default 4)
  TMDB 세마포어: meta_sources._sem_tmdb (12개 동시)

실행:
  python RAG/scripts/fill_missing_episodes.py
  python RAG/scripts/fill_missing_episodes.py --dry-run    # DB 변경 없음
  python RAG/scripts/fill_missing_episodes.py --resume     # 체크포인트 이어서
  python RAG/scripts/fill_missing_episodes.py --workers 8  # 워커 수 조정
  python RAG/scripts/fill_missing_episodes.py --limit 100  # 시리즈 100개만 테스트
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
import re
import json
import time
import argparse
import threading
import requests
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from tqdm import tqdm

# ── 경로 설정 ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "RAG" / "config" / "api_keys.env", override=False)

_SRC = ROOT / "RAG" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
import meta_sources as rab

# ── 상수 ───────────────────────────────────────────────────────────────────────
TARGET_CT_CL = ("TV드라마", "TV애니메이션", "키즈", "TV시사/교양")

CHECKPOINT_FILE = ROOT / "RAG" / "data" / "fill_episodes_checkpoint.json"
LOG_FILE        = ROOT / "RAG" / "data" / "fill_episodes.log"

_TMDB_URL       = "https://api.themoviedb.org/3"
REQUEST_TIMEOUT = 8

# 에피소드 번호 추출: "짱구는못말려 001회" → 1
_RE_EP_NUM = re.compile(r'(\d{2,4})회\s*$')


# ── DB 연결 ────────────────────────────────────────────────────────────────────
def _get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


# ── 체크포인트 ─────────────────────────────────────────────────────────────────
_ckpt_lock = threading.Lock()


def _load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {
        "done": [],
        "stats": {"searched": 0, "inserted": 0, "complete": 0, "no_tmdb": 0, "failed": 0},
    }


def _save_checkpoint(ckpt: dict):
    with _ckpt_lock:
        CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CHECKPOINT_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(ckpt, f, ensure_ascii=False, indent=2)
        tmp.replace(CHECKPOINT_FILE)


# ── synthetic full_asset_id ───────────────────────────────────────────────────
def _make_syn_id(tmdb_id: int, season: int, ep_num: int) -> str:
    """SYN|{tmdb_id:08d}|S{season:02d}E{ep_num:04d}  →  최대 28 chars (VARCHAR(64) 안전)."""
    return f"SYN|{tmdb_id:08d}|S{season:02d}E{ep_num:04d}"


# ── asset_nm 포맷 ──────────────────────────────────────────────────────────────
def _make_asset_nm(series_nm: str, cumulative_ep: int, total_eps: int) -> str:
    """총 에피소드 수 기준으로 자릿수 결정."""
    if total_eps > 99:
        return f"{series_nm} {cumulative_ep:03d}회"
    return f"{series_nm} {cumulative_ep:02d}회"


# ── TMDB 전체 에피소드 조회 ────────────────────────────────────────────────────
def _fetch_tmdb_episodes(tmdb_id: int) -> list[dict]:
    """TV 시리즈의 모든 시즌 에피소드를 누적 회차 번호와 함께 반환.

    Returns:
        [{"season": int, "ep_num_tmdb": int, "cumulative": int,
          "ep_name": str, "air_date": str|None}, ...]

    누적 번호(cumulative) 계산:
        시즌 1 ep 1~n1  → cumulative 1~n1
        시즌 2 ep 1~n2  → cumulative n1+1 ~ n1+n2
        …
    """
    # 시리즈 기본 정보로 시즌 목록 획득
    try:
        with rab._sem_tmdb:
            r = requests.get(
                f"{_TMDB_URL}/tv/{tmdb_id}",
                params=rab._tmdb_params({"language": "ko-KR"}),
                headers=rab._tmdb_headers(),
                timeout=REQUEST_TIMEOUT,
            )
        data = r.json()
    except Exception:
        return []

    # 시즌 0(스페셜) 제외, 번호 순 정렬
    seasons = sorted(
        [s for s in data.get("seasons", []) if s.get("season_number", 0) > 0],
        key=lambda s: s["season_number"],
    )

    all_eps = []
    cumulative_offset = 0

    for season_info in seasons:
        sn = season_info["season_number"]
        try:
            with rab._sem_tmdb:
                sr = requests.get(
                    f"{_TMDB_URL}/tv/{tmdb_id}/season/{sn}",
                    params=rab._tmdb_params({"language": "ko-KR"}),
                    headers=rab._tmdb_headers(),
                    timeout=REQUEST_TIMEOUT,
                )
            eps_in_season = [
                ep for ep in sr.json().get("episodes", [])
                if isinstance(ep.get("episode_number"), int) and ep["episode_number"] > 0
            ]
            eps_in_season.sort(key=lambda e: e["episode_number"])
            for ep in eps_in_season:
                en = ep["episode_number"]
                all_eps.append({
                    "season":      sn,
                    "ep_num_tmdb": en,
                    "cumulative":  cumulative_offset + en,
                    "ep_name":     ep.get("name") or "",
                    "air_date":    ep.get("air_date") or None,
                })
            # 다음 시즌 오프셋 = 이번 시즌 마지막 에피소드 번호 기준
            if eps_in_season:
                cumulative_offset += eps_in_season[-1]["episode_number"]
        except Exception:
            continue

    return all_eps


# ── 시리즈 1건 처리 (worker) ──────────────────────────────────────────────────
def _process_series(row: dict, dry_run: bool) -> dict:
    """
    Args:
        row: {
          series_nm, ct_cl, genre,
          existing_eps: set[int],       # DB에 있는 누적 에피소드 번호 set
          rep_row: {director, cast_lead, rating, smry, poster_url, disp_rtm}
        }
    Returns:
        {series_nm, status, inserted, tmdb_id, error}
    """
    series_nm = row["series_nm"]
    ct_cl     = row["ct_cl"]
    genre     = row.get("genre") or ""
    existing  = row["existing_eps"]
    rep       = row["rep_row"]

    result = {
        "series_nm": series_nm,
        "status": "ok",
        "inserted": 0,
        "tmdb_id": None,
        "error": None,
    }

    # ── 1. TMDB 검색 ────────────────────────────────────────────────────────
    tmdb_item = rab._tmdb_search(series_nm, series_nm, prefer_movie=False)
    if not tmdb_item or tmdb_item.get("media_type") != "tv":
        result["status"] = "no_tmdb"
        return result

    tmdb_id = tmdb_item["id"]
    result["tmdb_id"] = tmdb_id

    # ── 2. TMDB 에피소드 목록 ───────────────────────────────────────────────
    tmdb_eps = _fetch_tmdb_episodes(tmdb_id)
    if not tmdb_eps:
        result["status"] = "no_tmdb_eps"
        return result

    total_tmdb = len(tmdb_eps)

    # ── 3. 누락 에피소드 계산 ─────────────────────────────────────────────
    # existing이 비어있거나 전부 회차번호 파싱 실패인 경우:
    # 전체 TMDB 에피소드를 missing으로 간주
    missing = [ep for ep in tmdb_eps if ep["cumulative"] not in existing]

    if not missing:
        result["status"] = "complete"
        return result

    # ── 4. DRY-RUN ──────────────────────────────────────────────────────────
    if dry_run:
        result["status"] = "dry_run"
        result["inserted"] = len(missing)
        return result

    # ── 5. INSERT ───────────────────────────────────────────────────────────
    try:
        conn = _get_conn()
        cur = conn.cursor()
        inserted = 0

        for ep in missing:
            syn_id   = _make_syn_id(tmdb_id, ep["season"], ep["ep_num_tmdb"])
            asset_nm = _make_asset_nm(series_nm, ep["cumulative"], total_tmdb)

            cur.execute("""
                INSERT INTO public.vod (
                    full_asset_id, asset_nm, series_nm, ct_cl, genre,
                    director, cast_lead, rating, smry, poster_url, disp_rtm,
                    rag_processed, rag_source, rag_confidence
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    TRUE, 'TMDB_FILL', 0.85
                )
                ON CONFLICT (full_asset_id) DO NOTHING
            """, (
                syn_id,
                asset_nm,
                series_nm,
                ct_cl,
                genre,
                rep.get("director"),
                rep.get("cast_lead"),
                rep.get("rating"),
                rep.get("smry"),
                rep.get("poster_url"),
                rep.get("disp_rtm"),
            ))
            if cur.rowcount > 0:
                inserted += 1

        conn.commit()
        cur.close()
        conn.close()
        result["inserted"] = inserted

    except Exception as e:
        result["status"] = "db_error"
        result["error"] = str(e)

    return result


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="TMDB 에피소드 DB 채우기 파이프라인")
    parser.add_argument("--dry-run",  action="store_true", help="DB 변경 없이 분석만")
    parser.add_argument("--resume",   action="store_true", help="체크포인트에서 이어서 실행")
    parser.add_argument("--workers",  type=int, default=4, help="병렬 워커 수 (기본 4)")
    parser.add_argument("--limit",    type=int, default=0, help="처리할 시리즈 수 제한 (0=전체)")
    args = parser.parse_args()

    ckpt = _load_checkpoint() if args.resume else {
        "done": [],
        "stats": {"searched": 0, "inserted": 0, "complete": 0, "no_tmdb": 0, "failed": 0},
    }
    done_set = set(ckpt["done"])

    # ── DB: 시리즈별 현황 조회 ────────────────────────────────────────────
    print("DB에서 시리즈 현황 조회 중...", flush=True)
    conn = _get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    placeholders = ",".join(["%s"] * len(TARGET_CT_CL))
    cur.execute(f"""
        SELECT
            series_nm,
            ct_cl,
            MAX(genre)       AS genre,
            MAX(director)    AS director,
            MAX(cast_lead)   AS cast_lead,
            MAX(rating)      AS rating,
            MAX(smry)        AS smry,
            MAX(poster_url)  AS poster_url,
            MAX(disp_rtm)    AS disp_rtm,
            array_agg(asset_nm ORDER BY asset_nm) AS asset_names
        FROM public.vod
        WHERE ct_cl IN ({placeholders})
          AND series_nm IS NOT NULL
          AND series_nm <> ''
        GROUP BY series_nm, ct_cl
        ORDER BY series_nm
    """, TARGET_CT_CL)
    db_rows = cur.fetchall()
    cur.close()
    conn.close()

    print(f"전체 시리즈: {len(db_rows)}건", flush=True)

    # ── 처리 목록 구성 ────────────────────────────────────────────────────
    series_list = []
    for row in db_rows:
        sn = row["series_nm"]
        if sn in done_set:
            continue

        # 기존 에피소드 번호 추출 (asset_nm → 숫자)
        existing_eps: set[int] = set()
        for nm in (row["asset_names"] or []):
            if nm:
                m = _RE_EP_NUM.search(nm)
                if m:
                    existing_eps.add(int(m.group(1)))

        series_list.append({
            "series_nm":   sn,
            "ct_cl":       row["ct_cl"],
            "genre":       row["genre"],
            "existing_eps": existing_eps,
            "rep_row": {
                "director":  row["director"],
                "cast_lead": row["cast_lead"],
                "rating":    row["rating"],
                "smry":      row["smry"],
                "poster_url": row["poster_url"],
                "disp_rtm":  row["disp_rtm"],
            },
        })

    if args.limit > 0:
        series_list = series_list[: args.limit]

    total = len(series_list)
    print(f"처리 대상: {total}건  (완료 스킵: {len(done_set)}건)", flush=True)
    if args.dry_run:
        print("[DRY-RUN] DB에 쓰지 않고 INSERT 예상 건수만 계산합니다.", flush=True)
    print(f"워커: {args.workers}개", flush=True)

    # ── 병렬 처리 ─────────────────────────────────────────────────────────
    stats = ckpt["stats"]
    result_lock = threading.Lock()

    with tqdm(total=total, desc="시리즈 처리", unit="series", ncols=90) as pbar:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(_process_series, row, args.dry_run): row["series_nm"]
                for row in series_list
            }
            for future in as_completed(futures):
                series_nm = futures[future]
                try:
                    res = future.result()
                except Exception as e:
                    res = {
                        "series_nm": series_nm,
                        "status": "exception",
                        "inserted": 0,
                        "error": str(e),
                    }

                status   = res["status"]
                inserted = res.get("inserted", 0)

                with result_lock:
                    stats["searched"] += 1
                    stats["inserted"] += inserted

                    if status in ("ok", "dry_run") and inserted > 0:
                        tqdm.write(
                            f"[INSERT] {series_nm}: +{inserted}회"
                            + (" (dry)" if status == "dry_run" else "")
                        )
                    elif status == "complete":
                        stats["complete"] += 1
                    elif status in ("no_tmdb", "no_tmdb_eps"):
                        stats["no_tmdb"] += 1
                    elif status in ("db_error", "exception"):
                        stats["failed"] += 1
                        tqdm.write(f"[FAIL]   {series_nm}: {res.get('error')}")

                    ckpt["done"].append(series_nm)
                    ckpt["stats"] = stats

                    if stats["searched"] % 50 == 0:
                        _save_checkpoint(ckpt)

                pbar.update(1)

    _save_checkpoint(ckpt)

    print("\n" + "=" * 50)
    print(f"검색 완료 : {stats['searched']:,}건")
    print(f"INSERT    : {stats['inserted']:,}건  ({'예상' if args.dry_run else '실제'})")
    print(f"이미 완전 : {stats['complete']:,}건")
    print(f"TMDB 없음 : {stats['no_tmdb']:,}건")
    print(f"실패      : {stats['failed']:,}건")
    print(f"체크포인트: {CHECKPOINT_FILE}")


if __name__ == "__main__":
    main()
