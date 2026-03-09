"""
PLAN_00b Step 2: 접근법 A — 검색엔진 + Regex 방식으로 100건 배치 실행
입력: RAG/data/comparison_sample.csv
출력: RAG/reports/result_A.json
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import csv
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT_CSV = ROOT / "RAG" / "data" / "comparison_sample.csv"
OUTPUT_JSON = ROOT / "RAG" / "reports" / "result_A.json"

sys.path.insert(0, str(ROOT / "RAG" / "src"))
from search_functions import search_cast_lead, search_rating, search_release_date, search_director
from validation import validate_cast, validate_rating, validate_date, validate_director


def process_one(row: dict) -> dict:
    asset_nm = row["asset_nm"]
    genre = row.get("genre", "")
    t0 = time.time()

    result = {
        "full_asset_id": row["full_asset_id"],
        "asset_nm": asset_nm,
        "ct_cl": row["ct_cl"],
        "genre": genre,
        "cast_lead": None,
        "rating": None,
        "release_date": None,
        "director": None,
        "cast_lead_source": None,
        "rating_source": None,
        "release_date_source": None,
        "director_source": None,
        "elapsed_sec": 0.0,
        "error": None,
    }

    try:
        # cast_lead
        cast_list = search_cast_lead(asset_nm, genre)
        if cast_list and validate_cast(cast_list):
            result["cast_lead"] = json.dumps(cast_list, ensure_ascii=False)
            result["cast_lead_source"] = "Wikipedia/IMDB"

        # rating
        rating = search_rating(asset_nm)
        if rating and validate_rating(rating):
            result["rating"] = rating
            result["rating_source"] = "Wikipedia/IMDB"

        # release_date
        rel_date = search_release_date(asset_nm)
        if rel_date and validate_date(rel_date):
            result["release_date"] = rel_date
            result["release_date_source"] = "Wikipedia/IMDB"

        # director (already mostly filled, but check for completeness)
        if not row.get("director"):
            director = search_director(asset_nm)
            if director and validate_director(director):
                result["director"] = director
                result["director_source"] = "Wikipedia/IMDB"

    except Exception as e:
        result["error"] = str(e)

    result["elapsed_sec"] = round(time.time() - t0, 2)
    return result


def main():
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    with open(INPUT_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"접근법 A 시작: {len(rows)}건")
    results = []
    for i, row in enumerate(rows, 1):
        res = process_one(row)
        results.append(res)

        cast_ok = "O" if res["cast_lead"] else "-"
        rate_ok = "O" if res["rating"] else "-"
        date_ok = "O" if res["release_date"] else "-"
        err = f" ERR:{res['error'][:30]}" if res["error"] else ""
        print(f"[{i:3d}/100] {res['asset_nm'][:20]:20s} "
              f"cast={cast_ok} rate={rate_ok} date={date_ok} "
              f"{res['elapsed_sec']:.1f}s{err}")

    # 요약 통계
    n = len(results)
    cast_ok  = sum(1 for r in results if r["cast_lead"])
    rate_ok  = sum(1 for r in results if r["rating"])
    date_ok  = sum(1 for r in results if r["release_date"])
    dir_ok   = sum(1 for r in results if r["director"])
    avg_sec  = sum(r["elapsed_sec"] for r in results) / n
    errors   = sum(1 for r in results if r["error"])

    summary = {
        "approach": "A",
        "description": "검색엔진 + Regex (Wikipedia/IMDB)",
        "total": n,
        "cast_lead_found": cast_ok,
        "rating_found": rate_ok,
        "release_date_found": date_ok,
        "director_found": dir_ok,
        "cast_lead_rate": round(cast_ok / n, 3),
        "rating_rate": round(rate_ok / n, 3),
        "release_date_rate": round(date_ok / n, 3),
        "avg_elapsed_sec": round(avg_sec, 2),
        "errors": errors,
    }

    output = {"summary": summary, "results": results}
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n=== 접근법 A 완료 ===")
    print(f"cast_lead : {cast_ok}/{n} ({cast_ok/n*100:.1f}%)")
    print(f"rating    : {rate_ok}/{n} ({rate_ok/n*100:.1f}%)")
    print(f"release_dt: {date_ok}/{n} ({date_ok/n*100:.1f}%)")
    print(f"평균 시간  : {avg_sec:.2f}초/건")
    print(f"오류      : {errors}건")
    print(f"결과 저장  : {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
