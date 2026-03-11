"""
팀원 4명 작업 분할 스크립트
DB → VOD 목록 → dedup → 4개 JSON 파일 생성

분할 기준:
    A: TV 연예/오락 앞 절반 (full_asset_id 정렬 기준)  — 에피소드 단위
    B: TV 연예/오락 뒤 절반 (full_asset_id 정렬 기준)  — 에피소드 단위
    C: 영화 + TV드라마 + 키즈                          — 시리즈 dedup
    D: TV애니메이션 + TV 시사/교양 +
       기타 + 교육 + 다큐 + 스포츠 +
       공연/음악 + 라이프                               — 시리즈 dedup (해당 분류만)

실행:
    python scripts/split_tasks.py
    python scripts/split_tasks.py --out-dir data/tasks

팀원 실행 (출력 파일 생성 후):
    python scripts/crawl_trailers.py --task-file data/tasks_A.json
    python scripts/batch_embed.py --output parquet --out-file data/embeddings_A.parquet --delete-after-embed
"""

import sys
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.stdout.reconfigure(encoding='utf-8')

from crawl_trailers import (
    get_db_conn,
    EXCLUDE_CT_CL,
    SERIES_EMBED_CT_CL,
    dedup_by_series_nm,
)

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR     = PROJECT_ROOT / "data"

# 팀원별 담당 ct_cl
TEAM_C_CT_CL = {'영화', 'TV드라마', '키즈'}
TEAM_D_CT_CL = {'TV애니메이션', 'TV 시사/교양', '기타', '교육', '다큐', '스포츠', '공연/음악', '라이프'}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def split_half(vods: list) -> tuple:
    """full_asset_id 정렬 기준 앞 절반(A)·뒤 절반(B) 분할.
    홀수 건수일 때 뒤 절반이 1건 더 많다."""
    sorted_vods = sorted(vods, key=lambda v: v["vod_id"])
    mid = len(sorted_vods) // 2
    return sorted_vods[:mid], sorted_vods[mid:]


def fetch_all_vods() -> list:
    """vod 테이블 전체 조회 (제외 ct_cl 제거, ct_cl + full_asset_id 오름차순)."""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT full_asset_id, asset_nm, ct_cl, genre, series_nm "
            "FROM vod WHERE ct_cl NOT IN %s "
            "ORDER BY ct_cl, full_asset_id",
            (tuple(EXCLUDE_CT_CL),)
        )
        return [
            {"vod_id": r[0], "asset_nm": r[1], "ct_cl": r[2], "genre": r[3], "series_nm": r[4]}
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def save_task(vods: list, team: str, description: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"tasks_{team}.json"
    data = {
        "team": team,
        "description": description,
        "total": len(vods),
        "created_at": datetime.now().isoformat(),
        "vods": vods,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"  tasks_{team}.json : {len(vods):>6,}건  ({description})")
    return path


def main():
    parser = argparse.ArgumentParser(description="팀원 4명 작업 분할")
    parser.add_argument(
        '--out-dir', type=str, default=str(DATA_DIR),
        help=f'출력 디렉토리 (기본: {DATA_DIR})',
    )
    args = parser.parse_args()
    out_dir = Path(args.out_dir)

    log.info("DB에서 VOD 목록 조회 중...")
    all_vods = fetch_all_vods()
    log.info(f"전체 VOD: {len(all_vods):,}건 (우리동네·미분류 제외)")

    # ── 분류 ──────────────────────────────────────────────
    entertainment = [v for v in all_vods if v["ct_cl"] == 'TV 연예/오락']
    c_pool        = [v for v in all_vods if v["ct_cl"] in TEAM_C_CT_CL]
    d_pool        = [v for v in all_vods if v["ct_cl"] in TEAM_D_CT_CL]

    # A / B : TV 연예/오락 → full_asset_id 정렬 후 앞/뒤 절반 분할
    team_a, team_b = split_half(entertainment)

    # C : 영화 + TV드라마 + 키즈 → 시리즈 dedup
    team_c = dedup_by_series_nm(c_pool)

    # D : TV애니메이션 + TV 시사/교양 → 시리즈 dedup / 나머지는 그대로
    d_series = [v for v in d_pool if v["ct_cl"] in SERIES_EMBED_CT_CL]
    d_rest   = [v for v in d_pool if v["ct_cl"] not in SERIES_EMBED_CT_CL]
    team_d   = dedup_by_series_nm(d_series) + d_rest

    # ── 저장 ──────────────────────────────────────────────
    log.info("\n=== 분할 결과 ===")
    save_task(team_a, "A", "TV 연예/오락 (full_asset_id 정렬 앞 절반)", out_dir)
    save_task(team_b, "B", "TV 연예/오락 (full_asset_id 정렬 뒤 절반)", out_dir)
    save_task(team_c, "C", "영화 + TV드라마 + 키즈 (시리즈 dedup)", out_dir)
    save_task(team_d, "D",
              "TV애니메이션 + TV 시사/교양 + 기타 + 교육 + 다큐 + 스포츠 + 공연/음악 + 라이프", out_dir)

    total = len(team_a) + len(team_b) + len(team_c) + len(team_d)
    log.info(
        f"\n합계: {total:,}건  "
        f"(A:{len(team_a):,} / B:{len(team_b):,} / C:{len(team_c):,} / D:{len(team_d):,})"
    )

    log.info("\n팀원 실행 명령:")
    for t in ['A', 'B', 'C', 'D']:
        log.info(f"  python scripts/crawl_trailers.py --task-file {out_dir}/tasks_{t}.json")


if __name__ == "__main__":
    main()
