"""
pipelines/run_bulk_meta.py — 대량 처리 파이프라인 (TMDB→KMDB→JW→DATA_GO)
==========================================================================
핵심 최적화: 시리즈 레벨 dedup
  - 에피소드 100건이 같은 시리즈면 API 1번만 호출 (10× 감소)

Stage 1 (TMDB)    : unique 시리즈 전체 → 시리즈당 1회 API 호출
Stage 2 (KMDB)    : Stage1 미확보 시리즈만
Stage 3 (JW)      : Stage2 이후에도 미확보 시리즈만
Stage 4 (DATA_GO) : Stage3 이후에도 미확보 시리즈만
Final             : 시리즈 결과 → 건별 row 확장 → JSONL 저장

체크포인트: RAG/data/bulk/series_cache.json (--resume으로 재개 가능)

실행:
  python pipelines/run_bulk_meta.py --source db --output db
  python pipelines/run_bulk_meta.py --source db --resume --stages 234
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
import csv
import json
import time
import threading
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "RAG" / "config" / "api_keys.env", override=False)

_SRC = ROOT / "RAG" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
from sources import meta_sources as rab
from sources.validation import validate_cast

# ─── 경로 설정 ────────────────────────────────────────────────────
BULK_DIR    = ROOT / "RAG" / "data" / "bulk"
CACHE_FILE  = BULK_DIR / "series_cache.json"
FINAL_JSONL = BULK_DIR / "final_results.jsonl"
INPUT_CSV   = ROOT / "RAG" / "data" / "comparison_sample.csv"

TARGET_FIELDS = ["cast_lead", "director", "rating", "release_date", "smry", "series_nm", "disp_rtm"]

# Stage별 "아직 필요한 필드" 기준
_NEEDS_KMDB    = ["cast_lead", "rating", "disp_rtm", "director", "release_date"]
_NEEDS_JW      = ["rating", "disp_rtm", "director", "cast_lead", "smry"]
_NEEDS_DATA_GO = ["rating", "disp_rtm", "director", "cast_lead"]


# ─── 유틸 ─────────────────────────────────────────────────────────

def _needs_any(entry: dict, fields: list) -> bool:
    return any(not entry.get(f) for f in fields)


def _empty_entry() -> dict:
    return {
        "tmdb_id": None, "media_type": None,
        "cast_lead": None, "director": None, "rating": None,
        "release_date": None, "smry": None, "series_nm": None,
        "disp_rtm": None, "source": None,
        "stages_done": [],
    }


def _merge_into(entry: dict, patch: dict, fields: list, src_if_new: str) -> bool:
    """patch의 필드를 entry에 병합. 기여한 필드가 있으면 source 업데이트 후 True 반환."""
    contributed = False
    for field in fields:
        if not entry.get(field) and patch.get(field):
            entry[field] = patch[field]
            contributed = True
    if contributed:
        prev = entry.get("source") or ""
        entry["source"] = src_if_new if not prev else f"{prev}+{src_if_new}"
    return contributed


# ─── 체크포인트 I/O ───────────────────────────────────────────────

def _save_cache(cache: Dict[str, dict]) -> None:
    BULK_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    tmp.replace(CACHE_FILE)  # atomic replace


def _load_cache() -> Dict[str, dict]:
    if CACHE_FILE.exists():
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


# ─── Stage 1: TMDB ────────────────────────────────────────────────

def _tmdb_fetch_one(series: str, ct_cl: str, original: str) -> dict:
    prefer_movie = ct_cl in rab._MOVIE_TYPES
    item   = rab._tmdb_search(series, original, prefer_movie)
    entry  = _empty_entry()
    if item:
        detail = rab._tmdb_series_detail(item)
        if detail:
            entry.update({
                "tmdb_id":      item["id"],
                "media_type":   item["media_type"],
                "cast_lead":    rab._extract_cast(detail),
                "director":     rab._extract_director(detail),
                "release_date": rab._extract_release_date(detail),
                "rating":       rab._extract_rating(detail),
                "smry":         rab._extract_smry(detail),
                "series_nm":    rab._extract_series_nm(detail),
                "disp_rtm":     rab._extract_disp_rtm(detail),
                "source":       "TMDB",
            })
    entry["stages_done"].append("tmdb")
    return entry


def run_stage1_tmdb(series_meta: Dict[str, dict], cache: Dict[str, dict]) -> None:
    todo = {s: m for s, m in series_meta.items()
            if "tmdb" not in cache.get(s, {}).get("stages_done", [])}
    if not todo:
        print("Stage 1 (TMDB): 전체 캐시 히트 — 스킵")
        return

    print(f"Stage 1 (TMDB): {len(todo):,}개 시리즈 조회")
    lock = threading.Lock()

    def _fetch(series: str) -> tuple:
        m = todo[series]
        return series, _tmdb_fetch_one(series, m["ct_cl"], m["original"])

    with ThreadPoolExecutor(max_workers=rab.MAX_WORKERS) as ex:
        futures = {ex.submit(_fetch, s): s for s in todo}
        with tqdm(total=len(todo), desc="TMDB", unit="시리즈", ncols=80) as pbar:
            for f in as_completed(futures):
                series, result = f.result()
                with lock:
                    cache[series] = result
                pbar.update(1)

    _save_cache(cache)
    tmdb_hits = sum(1 for v in cache.values() if v.get("tmdb_id"))
    print(f"  → TMDB 매칭: {tmdb_hits:,}/{len(cache):,}개 ({tmdb_hits/len(cache)*100:.1f}%)")


# ─── Stage 2: KMDB ────────────────────────────────────────────────

def run_stage2_kmdb(series_meta: Dict[str, dict], cache: Dict[str, dict]) -> None:
    if not rab.KMDB_API_KEY:
        print("Stage 2 (KMDB): API 키 없음 — 스킵")
        return

    todo = {s for s in series_meta
            if "kmdb" not in cache.get(s, {}).get("stages_done", [])
            and _needs_any(cache.get(s, {}), _NEEDS_KMDB)}
    if not todo:
        print("Stage 2 (KMDB): 해당 없음 — 스킵")
        return

    print(f"Stage 2 (KMDB): {len(todo):,}개 시리즈 조회")
    lock = threading.Lock()

    def _fetch(series: str) -> tuple:
        item   = rab._kmdb_search(series)
        parsed = rab._parse_kmdb(item) if item else {}
        return series, parsed

    with ThreadPoolExecutor(max_workers=rab.SEM_KMDB_COUNT) as ex:
        futures = {ex.submit(_fetch, s): s for s in todo}
        with tqdm(total=len(todo), desc="KMDB", unit="시리즈", ncols=80) as pbar:
            for f in as_completed(futures):
                series, parsed = f.result()
                with lock:
                    entry = cache.setdefault(series, _empty_entry())
                    _merge_into(entry, parsed,
                                ["cast_lead", "director", "release_date", "rating", "disp_rtm"],
                                "KMDB" if not entry.get("tmdb_id") else "KMDB")
                    entry.setdefault("stages_done", []).append("kmdb")
                pbar.update(1)

    _save_cache(cache)
    kmdb_contributed = sum(1 for v in cache.values() if "KMDB" in (v.get("source") or ""))
    print(f"  → KMDB 기여: {kmdb_contributed:,}개 시리즈")


# ─── Stage 3: JustWatch ───────────────────────────────────────────

def run_stage3_jw(series_meta: Dict[str, dict], cache: Dict[str, dict]) -> None:
    todo = {s for s in series_meta
            if "jw" not in cache.get(s, {}).get("stages_done", [])
            and _needs_any(cache.get(s, {}), _NEEDS_JW)}
    if not todo:
        print("Stage 3 (JW): 해당 없음 — 스킵")
        return

    print(f"Stage 3 (JW): {len(todo):,}개 시리즈 조회")
    lock = threading.Lock()

    def _fetch(series: str) -> tuple:
        original = series_meta[series]["original"]
        return series, rab._jw_search(series, original)

    with ThreadPoolExecutor(max_workers=rab.SEM_JW_COUNT) as ex:
        futures = {ex.submit(_fetch, s): s for s in todo}
        with tqdm(total=len(todo), desc="JW", unit="시리즈", ncols=80) as pbar:
            for f in as_completed(futures):
                series, jw = f.result()
                with lock:
                    entry = cache.setdefault(series, _empty_entry())
                    _merge_into(entry, jw, _NEEDS_JW,
                                "JustWatch" if not entry.get("tmdb_id") else "JW")
                    entry.setdefault("stages_done", []).append("jw")
                pbar.update(1)

    _save_cache(cache)
    jw_contributed = sum(1 for v in cache.values() if "JW" in (v.get("source") or ""))
    print(f"  → JW 기여: {jw_contributed:,}개 시리즈")


# ─── Stage 4: DATA_GO ─────────────────────────────────────────────

def run_stage4_data_go(series_meta: Dict[str, dict], cache: Dict[str, dict]) -> None:
    if not rab.DATA_GO_API_KEY:
        print("Stage 4 (DATA_GO): API 키 없음 — 스킵")
        return

    todo = {s for s in series_meta
            if "data_go" not in cache.get(s, {}).get("stages_done", [])
            and _needs_any(cache.get(s, {}), _NEEDS_DATA_GO)}
    if not todo:
        print("Stage 4 (DATA_GO): 해당 없음 — 스킵")
        return

    print(f"Stage 4 (DATA_GO): {len(todo):,}개 시리즈 조회")
    lock = threading.Lock()

    def _fetch(series: str) -> tuple:
        return series, rab._data_go_search(series)

    with ThreadPoolExecutor(max_workers=rab.SEM_DATA_GO_COUNT) as ex:
        futures = {ex.submit(_fetch, s): s for s in todo}
        with tqdm(total=len(todo), desc="DATA_GO", unit="시리즈", ncols=80) as pbar:
            for f in as_completed(futures):
                series, dg = f.result()
                with lock:
                    entry = cache.setdefault(series, _empty_entry())
                    _merge_into(entry, dg, _NEEDS_DATA_GO,
                                "DATA_GO" if not entry.get("tmdb_id") else "DATA_GO")
                    entry.setdefault("stages_done", []).append("data_go")
                pbar.update(1)

    _save_cache(cache)
    dg_contributed = sum(1 for v in cache.values() if "DATA_GO" in (v.get("source") or ""))
    print(f"  → DATA_GO 기여: {dg_contributed:,}개 시리즈")


# ─── Final: 시리즈 결과 → 건별 확장 & JSONL 저장 ──────────────────

def expand_and_write(rows: List[dict], cache: Dict[str, dict]) -> dict:
    BULK_DIR.mkdir(parents=True, exist_ok=True)
    stats = {f: 0 for f in TARGET_FIELDS}
    stats["total"] = len(rows)

    with open(FINAL_JSONL, "w", encoding="utf-8") as out:
        for row in rows:
            series = rab._series_name(row["asset_nm"])
            data   = cache.get(series, {})
            src    = data.get("source") or ""

            result = {
                "full_asset_id": row["full_asset_id"],
                "asset_nm":      row["asset_nm"],
                "ct_cl":         row.get("ct_cl", ""),
                "tmdb_id":       data.get("tmdb_id"),
                "tmdb_media_type": data.get("media_type"),
            }

            for field in TARGET_FIELDS:
                val = data.get(field)
                if field == "cast_lead":
                    if val and validate_cast(val):
                        result[field]              = json.dumps(val, ensure_ascii=False)
                        result[f"{field}_source"]  = src
                        stats[field] += 1
                    else:
                        result[field]             = None
                        result[f"{field}_source"] = None
                elif val:
                    result[field]             = val
                    result[f"{field}_source"] = src
                    stats[field] += 1
                else:
                    result[field]             = None
                    result[f"{field}_source"] = None

            out.write(json.dumps(result, ensure_ascii=False) + "\n")

    return stats


# ─── 입력 소스 ────────────────────────────────────────────────────

def load_rows_csv() -> List[dict]:
    with open(INPUT_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_rows_db() -> List[dict]:
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "10.0.0.1"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "prod_db"),
        user=os.getenv("DB_USER", "dbadmin"),
        password=os.getenv("DB_PASSWORD", ""),
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT full_asset_id, asset_nm, ct_cl, genre
        FROM vod
        WHERE cast_lead   IS NULL
           OR director    IS NULL
           OR rating      IS NULL
           OR release_date IS NULL
           OR smry        IS NULL
           OR disp_rtm    IS NULL
        ORDER BY full_asset_id
    """)
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


# ─── DB UPDATE ────────────────────────────────────────────────────
# vod 테이블의 실제 컬럼명에 맞게 수정 필요
_DB_COLUMN_MAP = {
    "cast_lead":    "cast_lead",
    "director":     "director",
    "rating":       "rating",
    "release_date": "release_date",
    "smry":         "smry",
    "series_nm":    "series_nm",
    "disp_rtm":     "disp_rtm",
}


def update_db(batch_size: int = 500) -> int:
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "10.0.0.1"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "prod_db"),
        user=os.getenv("DB_USER", "dbadmin"),
        password=os.getenv("DB_PASSWORD", ""),
    )
    cur = conn.cursor()
    updated = 0

    batch: list = []
    with open(FINAL_JSONL, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            fields_to_update = {
                _DB_COLUMN_MAP[k]: row[k]
                for k in TARGET_FIELDS
                if row.get(k) and k in _DB_COLUMN_MAP
            }
            if not fields_to_update:
                continue
            batch.append((fields_to_update, row.get("cast_lead_source") or "", row["full_asset_id"]))

            if len(batch) >= batch_size:
                _flush_batch(cur, batch)
                conn.commit()
                updated += len(batch)
                batch = []

    if batch:
        _flush_batch(cur, batch)
        conn.commit()
        updated += len(batch)

    cur.close()
    conn.close()
    return updated


def _flush_batch(cur, batch: list) -> None:
    for fields_to_update, rag_source, full_asset_id in batch:
        set_clause = ", ".join(f"{col} = %s" for col in fields_to_update)
        values = list(fields_to_update.values()) + [rag_source, full_asset_id]
        cur.execute(
            f"UPDATE vod SET {set_clause}, "
            f"rag_processed = TRUE, rag_source = %s, rag_processed_at = NOW() "
            f"WHERE full_asset_id = %s",
            values,
        )


# ─── 메인 ─────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Bulk 수평 분할 파이프라인 (160k건 대량 처리)")
    ap.add_argument("--source",  choices=["csv", "db"],   default="csv",
                    help="입력 소스 (csv: 파일럿용, db: 전체 처리)")
    ap.add_argument("--output",  choices=["jsonl", "db"], default="jsonl",
                    help="출력 대상 (jsonl: 검증용, db: DB UPDATE)")
    ap.add_argument("--resume",  action="store_true",
                    help="이전 series_cache.json 체크포인트부터 재개")
    ap.add_argument("--stages",  default="1234",
                    help="실행할 Stage 번호 (예: '1234' 또는 '34')")
    args = ap.parse_args()

    t_start = time.time()
    BULK_DIR.mkdir(parents=True, exist_ok=True)

    # ── 입력 로드 ──
    print(f"[입력] source={args.source}")
    rows = load_rows_db() if args.source == "db" else load_rows_csv()
    print(f"  대상: {len(rows):,}건")

    # ── unique 시리즈 추출 (dedup 핵심) ──
    series_meta: Dict[str, dict] = {}
    for row in rows:
        s = rab._series_name(row["asset_nm"])
        if s not in series_meta:
            series_meta[s] = {"ct_cl": row.get("ct_cl", ""), "original": row["asset_nm"]}

    dedup_ratio = len(rows) / max(len(series_meta), 1)
    print(f"  unique 시리즈: {len(series_meta):,}개  (dedup {dedup_ratio:.1f}x — API 호출 {dedup_ratio:.1f}배 감소)")

    # ── 체크포인트 로드 ──
    cache: Dict[str, dict] = {}
    if args.resume:
        cache = _load_cache()
        print(f"  체크포인트 로드: {len(cache):,}개 시리즈 캐시됨")
    else:
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()  # 신규 실행 시 이전 캐시 삭제

    # ── Stage 실행 ──
    print()
    if "1" in args.stages:
        run_stage1_tmdb(series_meta, cache)
        print()
    if "2" in args.stages:
        run_stage2_kmdb(series_meta, cache)
        print()
    if "3" in args.stages:
        run_stage3_jw(series_meta, cache)
        print()
    if "4" in args.stages:
        run_stage4_data_go(series_meta, cache)
        print()

    # ── Final: 시리즈 결과 → 건별 확장 ──
    print("Final: 시리즈 결과 → 건별 확장 중...")
    stats = expand_and_write(rows, cache)

    # ── 결과 출력 ──
    elapsed = time.time() - t_start
    n = stats["total"]
    print(f"\n{'='*50}")
    print(f"Bulk 파이프라인 완료  ({elapsed:.0f}초 / {elapsed/60:.1f}분)")
    print(f"{'='*50}")
    print(f"  {'컬럼':<15} {'성공':>6}  {'비율':>6}")
    print(f"  {'-'*30}")
    for field in TARGET_FIELDS:
        cnt = stats[field]
        print(f"  {field:<15} {cnt:>6}/{n}  ({cnt/n*100:.1f}%)")

    print(f"\n  시리즈 캐시  : {CACHE_FILE}")
    print(f"  결과 JSONL   : {FINAL_JSONL}")

    # ── 소스별 분포 ──
    src_dist: Dict[str, int] = {}
    for v in cache.values():
        src = v.get("source") or "미매칭"
        src_dist[src] = src_dist.get(src, 0) + 1
    print(f"\n  소스 분포 (상위 10):")
    for src, cnt in sorted(src_dist.items(), key=lambda x: -x[1])[:10]:
        print(f"    {src:<30} {cnt:>5}개")

    # ── DB UPDATE ──
    if args.output == "db":
        print("\nDB UPDATE 중...")
        updated = update_db()
        print(f"  → {updated:,}건 UPDATE 완료")


if __name__ == "__main__":
    main()
