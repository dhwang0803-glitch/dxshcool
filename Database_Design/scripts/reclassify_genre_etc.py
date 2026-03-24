"""
genre='기타' 18,902건을 genre_detail + ct_cl 기반으로 재분류

기존 genre 값 체계를 최대한 재활용하고,
매핑 불가능한 항목은 genre='기타'를 유지한다.

실행:
    conda activate myenv
    python Database_Design/scripts/reclassify_genre_etc.py --dry-run    # 변경 미리보기
    python Database_Design/scripts/reclassify_genre_etc.py              # 실제 적용
    python Database_Design/scripts/reclassify_genre_etc.py --rollback   # 원복
"""

import sys
import os
import argparse
import logging
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ── DB ──────────────────────────────────────────────────────────

def load_env():
    env = {}
    for p in [PROJECT_ROOT / ".env", PROJECT_ROOT / "Database_Design" / ".env"]:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env[k.strip()] = v.strip()
            break
    return env


def get_conn():
    import psycopg2
    env = load_env()
    return psycopg2.connect(
        host=env.get("DB_HOST"),
        port=env.get("DB_PORT", 5432),
        dbname=env.get("DB_NAME"),
        user=env.get("DB_USER"),
        password=env.get("DB_PASSWORD"),
    )


# ── 매핑 규칙 ──────────────────────────────────────────────────
#
# 1순위: genre_detail 직접 매핑 (가장 정확)
# 2순위: ct_cl 기반 폴백 (genre_detail이 채널명일 때)
# 매핑 값이 None이면 '기타' 유지

GENRE_DETAIL_MAP = {
    # ── 키즈 동요/동화/학습 → 학습 ──
    "동요-동화":        "학습",
    "동요":            "학습",
    "동화":            "학습",
    "동화놀이학습":      "학습",
    "영어-놀이학습":     "학습",
    "영어학습":         "학습",
    "EBS키즈":         "학습",
    "핑크퐁TV":         "학습",
    "뽀로로동요":       "학습",
    "타요띠띠뽀동요":    "학습",
    "신기한나라TV":      "학습",
    "장난감놀이":       "학습",
    "LG사이언스랜드":    "학습",

    # ── 키즈 애니/놀이 → 애니메이션 ──
    "만화동산":         "애니메이션",
    "투니버스월정액":    "애니메이션",
    "(HD)애니플러스":    "애니메이션",
    "애니":            "애니메이션",
    "극장판애니메이션":   "애니메이션",
    "뽀로로애니메이션":   "애니메이션",
    "뽀로로TV오리지널":   "애니메이션",
    "뽀로로스페셜":      "애니메이션",
    "타요띠띠뽀애니메이션": "애니메이션",
    "뽀로로TV오리지널":   "애니메이션",
    "BBC키즈":          "애니메이션",

    # ── 키즈 엔터테인먼트 → 연예/오락 ──
    "캐리TV":          "연예/오락",
    "아이들나라":       "연예/오락",

    # ── 게임 콘텐츠 → 연예/오락 ──
    "게임애니팩토리":    "연예/오락",
    "게임":            "연예/오락",

    # ── 방송사 구작/채널 → 연예/오락 ──
    "SBS구작":         "연예/오락",
    "MBC구작":         "연예/오락",
    "MBCevery1":       "연예/오락",
    "IHQ무제한":        "연예/오락",
    "KBSN":            "연예/오락",
    "SBSPlus":         "연예/오락",
    "E채널":           "연예/오락",
    "TV조선":          "연예/오락",
    "케이블 연예오락":   "연예/오락",
    "버라이어티":       "연예/오락",
    "예능":            "연예/오락",
    "JTBC예능":        "연예/오락",

    # ── 장르 직접 매핑 ──
    "액션모험":         "액션/모험",
    "액션모험어린이":    "액션/모험",
    "코믹":            "명랑/코믹",
    "코믹어린이":       "명랑/코믹",
    "학원,순정":        "학원/순정/연애",
    "학원,순정어린이":   "학원/순정/연애",
    "추리,판타지":      "추리/미스터리",
    "추리,판타지어린이":  "추리/미스터리",
    "판타지":          "무협/환타지",
    "사극":            "드라마",
    "멜로로맨스":       "멜로",

    # ── 스포츠 ──
    "바둑":            "스포츠",
    "등산":            "스포츠",

    # ── 음악 ──
    "뮤직비디오":       "음악",
    "(HD)해외공연실황":  "음악",

    # ── 교양/다큐 ──
    "다큐교양":         "교양다큐",
    "JTBC시사교양":     "시사/교양",
    "KTV":             "시사/교양",
    "경제경영":         "시사/교양",

    # ── 영화 관련 채널 → 영화 ──
    "무비n시리즈":      "영화",
    "캐치온디맨드":     "영화",
    "캐치온라이트":     "영화",
    "(HD)평생소장":     "영화",
    "해외영화":         "영화",
    "국내영화":         "영화",
    "레드무비":         "성인",
    "UHD영화":          "영화",

    # ── 드라마 ──
    "국내드라마":       "드라마",
    "케이블 드라마":    "드라마",

    # ── 기타/라이프 ──
    "뷰티건강다이어트":  "연예/오락",
    "무료 라이프관":    "연예/오락",
    "가이드채널":       "연예/오락",
    "방송대상수상작":   "연예/오락",

    # ── 매핑 불가 → 기타 유지 ──
    "정보미상":         None,
    "기타":            None,
}

# 2순위: genre_detail이 매핑에 없을 때 ct_cl 기반 폴백
CT_CL_FALLBACK = {
    "키즈":          "애니메이션",
    "TV애니메이션":   "애니메이션",
    "스포츠":        "스포츠",
    "공연/음악":     "음악",
    "교육":          "교양다큐",
    "라이프":        "연예/오락",
    # "기타", "영화", "미분류", "우리동네" → None (기타 유지)
}


# ── 실행 ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="genre='기타' 재분류")
    parser.add_argument("--dry-run", action="store_true", help="변경 미리보기만 (DB 수정 없음)")
    parser.add_argument("--rollback", action="store_true", help="genre_detail='__backup_기타'에서 원복")
    args = parser.parse_args()

    conn = get_conn()
    cur = conn.cursor()

    if args.rollback:
        cur.execute("SELECT COUNT(*) FROM vod WHERE genre_detail LIKE '__backup_기타_%%'")
        cnt = cur.fetchone()[0]
        if cnt == 0:
            log.info("롤백 대상 없음 (백업 마커 없음)")
            return
        cur.execute("""
            UPDATE vod SET genre = '기타'
            WHERE genre_detail LIKE '__backup_기타_%%'
        """)
        cur.execute("""
            UPDATE vod SET genre_detail = REPLACE(genre_detail, '__backup_기타_', '')
            WHERE genre_detail LIKE '__backup_기타_%%'
        """)
        conn.commit()
        log.info(f"롤백 완료: {cnt}건 → genre='기타' 원복")
        cur.close()
        conn.close()
        return

    # 현재 genre='기타' 전체 조회
    cur.execute("""
        SELECT full_asset_id, genre_detail, ct_cl
        FROM vod
        WHERE genre = '기타'
    """)
    rows = cur.fetchall()
    log.info(f"genre='기타' 총 {len(rows):,}건 대상")

    # 매핑 계산
    updates = {}  # new_genre → [(asset_id, genre_detail), ...]
    unmapped = {}  # genre_detail → count

    for asset_id, gd, ct_cl in rows:
        new_genre = None

        # 1순위: genre_detail 직접 매핑
        if gd in GENRE_DETAIL_MAP:
            new_genre = GENRE_DETAIL_MAP[gd]

        # 2순위: ct_cl 폴백
        if new_genre is None and ct_cl in CT_CL_FALLBACK:
            new_genre = CT_CL_FALLBACK[ct_cl]

        if new_genre:
            updates.setdefault(new_genre, []).append((asset_id, gd))
        else:
            unmapped[gd] = unmapped.get(gd, 0) + 1

    # 결과 요약
    total_mapped = sum(len(v) for v in updates.items())
    total_unmapped = sum(unmapped.values())

    print(f"\n{'='*60}")
    print(f"재분류 결과 요약")
    print(f"{'='*60}")
    print(f"  전체 대상:    {len(rows):>8,}건")
    print(f"  재분류 대상:  {total_mapped:>8,}건")
    print(f"  기타 유지:    {total_unmapped:>8,}건")
    print()

    print(f"{'새 genre':<20s} | {'건수':>8s} | 주요 genre_detail")
    print(f"{'-'*20}-+-{'-'*8}-+-{'-'*40}")
    for genre, items in sorted(updates.items(), key=lambda x: -len(x[1])):
        # 주요 genre_detail 집계
        gd_counts = {}
        for _, gd in items:
            gd_counts[gd] = gd_counts.get(gd, 0) + 1
        top_gds = sorted(gd_counts.items(), key=lambda x: -x[1])[:3]
        top_str = ", ".join(f"{g}({c})" for g, c in top_gds)
        print(f"{genre:<20s} | {len(items):>8,} | {top_str}")

    if unmapped:
        print(f"\n기타 유지 항목:")
        for gd, cnt in sorted(unmapped.items(), key=lambda x: -x[1]):
            print(f"  {gd or '(NULL)':30s} | {cnt:>6,}")

    if args.dry_run:
        print(f"\n[DRY-RUN] DB 변경 없음. --dry-run 제거 후 재실행하세요.")
        cur.close()
        conn.close()
        return

    # 실제 UPDATE 실행
    print(f"\nDB 업데이트 시작...")

    total_updated = 0
    for new_genre, items in updates.items():
        asset_ids = [aid for aid, _ in items]

        # 배치 UPDATE
        batch_size = 5000
        for i in range(0, len(asset_ids), batch_size):
            batch = asset_ids[i:i + batch_size]
            cur.execute("""
                UPDATE vod SET genre = %s
                WHERE full_asset_id = ANY(%s)
                  AND genre = '기타'
            """, (new_genre, batch))
            total_updated += cur.rowcount

    conn.commit()
    log.info(f"UPDATE 완료: {total_updated:,}건 재분류")

    # 결과 검증
    cur.execute("SELECT genre, COUNT(*) FROM vod WHERE genre = '기타' GROUP BY genre")
    remaining = cur.fetchone()
    if remaining:
        log.info(f"잔여 genre='기타': {remaining[1]:,}건")

    cur.execute("""
        SELECT genre, COUNT(*) AS cnt FROM vod
        GROUP BY genre ORDER BY cnt DESC LIMIT 20
    """)
    print(f"\n{'='*60}")
    print(f"업데이트 후 genre 분포 (상위 20)")
    print(f"{'='*60}")
    for r in cur.fetchall():
        print(f"  {r[0]:20s} | {r[1]:>8,}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
