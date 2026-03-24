"""
테스터 계정 12명 생성 스크립트

군집 분석 기반 4개 페르소나 × 4개 연령대 (30대/40대/50대/60대)
- 군집0 저관여 구독자: 시청 10~15건, 완주율 낮음
- 군집1 핵심충성 구독자: 시청 40~50건, 완주율 높음, 장르 다양
- 군집2 헤비홈뷰어: 시청 50건+, 시청시간 긺, inhome_rate 높음
- 군집3 키즈가구: 키즈 콘텐츠 비중 높음 + 성인 콘텐츠 혼합

사용법:
    python scripts/create_test_users.py              # 실행 (DB 적재)
    python scripts/create_test_users.py --dry-run     # DB 저장 없이 확인만
"""
import argparse
import hashlib
import os
import random
import sys
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
# 테스터 페르소나 정의
# ──────────────────────────────────────────────

TESTERS = [
    # 군집0: 저관여 구독자 (2명)
    {
        "label": "C0_저관여_50대",
        "age_grp10": "50대", "inhome_rate": 35.0,
        "svod_scrb_cnt_grp": "1건", "paid_chnl_cnt_grp": "0건",
        "ch_hh_avg_month1": 50.0, "kids_use_pv_month1": 0.0,
        "nfx_use_yn": False,
        "watch_count": 12, "completion_range": (0.1, 0.4),
        "satisfaction_range": (0.2, 0.5),
        "ct_cl_weights": {"TV드라마": 0.5, "영화": 0.3, "TV 연예/오락": 0.2},
    },
    {
        "label": "C0_저관여_60대",
        "age_grp10": "60대", "inhome_rate": 40.0,
        "svod_scrb_cnt_grp": "0건", "paid_chnl_cnt_grp": "0건",
        "ch_hh_avg_month1": 30.0, "kids_use_pv_month1": 0.0,
        "nfx_use_yn": False,
        "watch_count": 10, "completion_range": (0.1, 0.35),
        "satisfaction_range": (0.15, 0.45),
        "ct_cl_weights": {"TV드라마": 0.6, "영화": 0.2, "TV 연예/오락": 0.2},
    },
    # 군집1: 핵심 충성 구독자 (4명)
    {
        "label": "C1_충성_50대",
        "age_grp10": "50대", "inhome_rate": 60.0,
        "svod_scrb_cnt_grp": "2건", "paid_chnl_cnt_grp": "1건",
        "ch_hh_avg_month1": 150.0, "kids_use_pv_month1": 0.0,
        "nfx_use_yn": True,
        "watch_count": 45, "completion_range": (0.7, 1.0),
        "satisfaction_range": (0.6, 0.95),
        "ct_cl_weights": {"TV드라마": 0.4, "영화": 0.35, "TV 연예/오락": 0.25},
    },
    {
        "label": "C1_충성_40대",
        "age_grp10": "40대", "inhome_rate": 55.0,
        "svod_scrb_cnt_grp": "3건이상", "paid_chnl_cnt_grp": "1건",
        "ch_hh_avg_month1": 130.0, "kids_use_pv_month1": 2.0,
        "nfx_use_yn": True,
        "watch_count": 50, "completion_range": (0.65, 0.95),
        "satisfaction_range": (0.55, 0.9),
        "ct_cl_weights": {"TV드라마": 0.35, "영화": 0.35, "TV 연예/오락": 0.3},
    },
    {
        "label": "C1_충성_30대",
        "age_grp10": "30대", "inhome_rate": 45.0,
        "svod_scrb_cnt_grp": "2건", "paid_chnl_cnt_grp": "0건",
        "ch_hh_avg_month1": 100.0, "kids_use_pv_month1": 0.0,
        "nfx_use_yn": True,
        "watch_count": 40, "completion_range": (0.6, 0.95),
        "satisfaction_range": (0.5, 0.85),
        "ct_cl_weights": {"TV드라마": 0.3, "영화": 0.4, "TV 연예/오락": 0.3},
    },
    {
        "label": "C1_충성_60대",
        "age_grp10": "60대", "inhome_rate": 70.0,
        "svod_scrb_cnt_grp": "2건", "paid_chnl_cnt_grp": "2건이상",
        "ch_hh_avg_month1": 180.0, "kids_use_pv_month1": 0.0,
        "nfx_use_yn": False,
        "watch_count": 42, "completion_range": (0.7, 1.0),
        "satisfaction_range": (0.6, 0.9),
        "ct_cl_weights": {"TV드라마": 0.5, "영화": 0.3, "TV 연예/오락": 0.2},
    },
    # 군집2: 헤비 홈뷰어 (3명)
    {
        "label": "C2_헤비_50대",
        "age_grp10": "50대", "inhome_rate": 90.0,
        "svod_scrb_cnt_grp": "3건이상", "paid_chnl_cnt_grp": "2건이상",
        "ch_hh_avg_month1": 250.0, "kids_use_pv_month1": 0.0,
        "nfx_use_yn": True,
        "watch_count": 60, "completion_range": (0.5, 0.9),
        "satisfaction_range": (0.5, 0.85),
        "ct_cl_weights": {"TV드라마": 0.4, "영화": 0.3, "TV 연예/오락": 0.2, "라이프": 0.1},
    },
    {
        "label": "C2_헤비_40대",
        "age_grp10": "40대", "inhome_rate": 85.0,
        "svod_scrb_cnt_grp": "3건이상", "paid_chnl_cnt_grp": "1건",
        "ch_hh_avg_month1": 220.0, "kids_use_pv_month1": 3.0,
        "nfx_use_yn": True,
        "watch_count": 55, "completion_range": (0.45, 0.85),
        "satisfaction_range": (0.45, 0.8),
        "ct_cl_weights": {"TV드라마": 0.35, "영화": 0.35, "TV 연예/오락": 0.2, "라이프": 0.1},
    },
    {
        "label": "C2_헤비_30대",
        "age_grp10": "30대", "inhome_rate": 80.0,
        "svod_scrb_cnt_grp": "3건이상", "paid_chnl_cnt_grp": "1건",
        "ch_hh_avg_month1": 200.0, "kids_use_pv_month1": 0.0,
        "nfx_use_yn": True,
        "watch_count": 55, "completion_range": (0.4, 0.85),
        "satisfaction_range": (0.4, 0.8),
        "ct_cl_weights": {"TV드라마": 0.3, "영화": 0.4, "TV 연예/오락": 0.2, "라이프": 0.1},
    },
    # 군집3: 키즈 가구 (3명)
    {
        "label": "C3_키즈_40대",
        "age_grp10": "40대", "inhome_rate": 65.0,
        "svod_scrb_cnt_grp": "2건", "paid_chnl_cnt_grp": "1건",
        "ch_hh_avg_month1": 120.0, "kids_use_pv_month1": 80.0,
        "nfx_use_yn": True,
        "watch_count": 35, "completion_range": (0.5, 0.9),
        "satisfaction_range": (0.5, 0.85),
        "ct_cl_weights": {"키즈": 0.5, "TV드라마": 0.25, "영화": 0.15, "TV 연예/오락": 0.1},
    },
    {
        "label": "C3_키즈_30대",
        "age_grp10": "30대", "inhome_rate": 60.0,
        "svod_scrb_cnt_grp": "2건", "paid_chnl_cnt_grp": "0건",
        "ch_hh_avg_month1": 100.0, "kids_use_pv_month1": 60.0,
        "nfx_use_yn": True,
        "watch_count": 30, "completion_range": (0.45, 0.85),
        "satisfaction_range": (0.45, 0.8),
        "ct_cl_weights": {"키즈": 0.45, "TV드라마": 0.25, "영화": 0.2, "TV 연예/오락": 0.1},
    },
    {
        "label": "C3_키즈_60대",
        "age_grp10": "60대", "inhome_rate": 70.0,
        "svod_scrb_cnt_grp": "1건", "paid_chnl_cnt_grp": "1건",
        "ch_hh_avg_month1": 90.0, "kids_use_pv_month1": 40.0,
        "nfx_use_yn": False,
        "watch_count": 25, "completion_range": (0.5, 0.85),
        "satisfaction_range": (0.5, 0.8),
        "ct_cl_weights": {"키즈": 0.4, "TV드라마": 0.35, "영화": 0.15, "TV 연예/오락": 0.1},
    },
]

# 테스터 sha2_hash 접두사 (식별 용이)
_TESTER_PREFIX = "test_"


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def generate_sha2(label: str) -> str:
    """테스터 label로부터 결정적 sha2_hash 생성."""
    return hashlib.sha256((_TESTER_PREFIX + label).encode()).hexdigest()


def fetch_vod_pool(conn) -> dict[str, list[str]]:
    """
    ct_cl별 완전 데이터 VOD 풀 조회.
    조건: poster_url 존재 + 메타 임베딩 존재 + CLIP 임베딩 존재
    → CF/Vector_Search 추천에 모두 활용 가능한 VOD만 선정
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT v.full_asset_id, v.ct_cl
        FROM public.vod v
        JOIN public.vod_meta_embedding vme ON v.full_asset_id = vme.vod_id_fk
        JOIN public.vod_embedding ve ON v.full_asset_id = ve.vod_id_fk
            AND ve.model_name = 'clip-ViT-B-32'
        WHERE v.poster_url IS NOT NULL AND v.poster_url != ''
          AND v.asset_nm IS NOT NULL
          AND v.ct_cl IS NOT NULL
        ORDER BY v.ct_cl, RANDOM()
    """)
    pool: dict[str, list[str]] = {}
    for vod_id, ct_cl in cur.fetchall():
        pool.setdefault(ct_cl, []).append(vod_id)
    cur.close()

    print("[VOD 풀]")
    for ct_cl, vods in sorted(pool.items(), key=lambda x: -len(x[1])):
        print(f"  {ct_cl}: {len(vods):,}건")

    return pool


def pick_watch_history(
    tester: dict,
    vod_pool: dict[str, list[str]],
    rng: random.Random,
) -> list[dict]:
    """테스터 설정에 따라 watch_history 레코드 생성."""
    sha2 = generate_sha2(tester["label"])
    count = tester["watch_count"]
    weights = tester["ct_cl_weights"]
    comp_lo, comp_hi = tester["completion_range"]
    sat_lo, sat_hi = tester["satisfaction_range"]

    # ct_cl별 시청 건수 분배
    ct_cl_counts: dict[str, int] = {}
    remaining = count
    ct_cls = list(weights.keys())
    for i, ct_cl in enumerate(ct_cls):
        if i == len(ct_cls) - 1:
            ct_cl_counts[ct_cl] = remaining
        else:
            n = max(1, round(count * weights[ct_cl]))
            ct_cl_counts[ct_cl] = n
            remaining -= n
    # remaining이 음수가 되면 마지막 항목 보정
    if ct_cl_counts[ct_cls[-1]] < 1:
        ct_cl_counts[ct_cls[-1]] = 1

    # VOD 선택 + watch_history 레코드 생성
    records = []
    base_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
    used_vods: set[str] = set()

    for ct_cl, n in ct_cl_counts.items():
        available = vod_pool.get(ct_cl, [])
        if not available:
            print(f"  [WARN] '{ct_cl}' VOD 없음 — {tester['label']}에서 건너뜀")
            continue
        # 풀에서 중복 없이 선택 (풀 부족 시 가능한 만큼)
        candidates = [v for v in available if v not in used_vods]
        if len(candidates) < n:
            print(f"  [WARN] '{ct_cl}' 후보 {len(candidates)}건 < 요청 {n}건 — 가능한 만큼만 선택")
            n = len(candidates)
        if n == 0:
            continue
        selected = rng.sample(candidates, n)
        used_vods.update(selected)

        for vod_id in selected:
            strt_dt = base_date + timedelta(
                days=rng.randint(0, 80),
                hours=rng.randint(8, 23),
                minutes=rng.randint(0, 59),
            )
            completion = round(rng.uniform(comp_lo, comp_hi), 4)
            satisfaction = round(rng.uniform(sat_lo, sat_hi), 4)
            # use_tms: 평균 3600초(1시간) 기준, 완주율에 비례
            use_tms = round(3600 * completion * rng.uniform(0.8, 1.2), 1)

            records.append({
                "user_id_fk": sha2,
                "vod_id_fk": vod_id,
                "strt_dt": strt_dt,
                "use_tms": use_tms,
                "completion_rate": completion,
                "satisfaction": satisfaction,
            })

    return records


def main():
    parser = argparse.ArgumentParser(description="테스터 계정 12명 생성")
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 없이 확인만")
    parser.add_argument("--seed", type=int, default=42, help="랜덤 시드 (기본 42)")
    args = parser.parse_args()

    rng = random.Random(args.seed)

    conn = get_connection()
    try:
        # 1. VOD 풀 조회
        print("=" * 60)
        print("테스터 계정 생성 시작")
        print("=" * 60)
        vod_pool = fetch_vod_pool(conn)

        if not vod_pool:
            print("[ERROR] 완전 데이터 VOD가 없습니다. 파이프라인 실행 후 재시도하세요.")
            sys.exit(1)

        # 2. user + watch_history 레코드 생성
        user_records = []
        all_watch_records = []

        for tester in TESTERS:
            sha2 = generate_sha2(tester["label"])
            user_records.append({
                "sha2_hash": sha2,
                "age_grp10": tester["age_grp10"],
                "inhome_rate": tester["inhome_rate"],
                "svod_scrb_cnt_grp": tester["svod_scrb_cnt_grp"],
                "paid_chnl_cnt_grp": tester["paid_chnl_cnt_grp"],
                "ch_hh_avg_month1": tester["ch_hh_avg_month1"],
                "kids_use_pv_month1": tester["kids_use_pv_month1"],
                "nfx_use_yn": tester["nfx_use_yn"],
            })
            watch_records = pick_watch_history(tester, vod_pool, rng)
            all_watch_records.extend(watch_records)
            print(f"  [{tester['label']}] sha2={sha2[:16]}... | 시청 {len(watch_records)}건")

        print(f"\n총 user: {len(user_records)}명, watch_history: {len(all_watch_records)}건")

        if args.dry_run:
            print("\n[dry-run] DB 저장 생략")
            # 샘플 출력
            for ur in user_records:
                print(f"  USER {ur['sha2_hash'][:16]}... {ur['age_grp10']}")
            return

        # 3. DB 적재
        cur = conn.cursor()

        # 기존 테스터 정리 (재실행 가능하도록)
        tester_hashes = [ur["sha2_hash"] for ur in user_records]
        print("\n[DB] 기존 테스터 데이터 정리...")
        cur.execute(
            'DELETE FROM public.watch_history WHERE user_id_fk = ANY(%s)',
            (tester_hashes,)
        )
        print(f"  watch_history 삭제: {cur.rowcount}건")
        cur.execute(
            'DELETE FROM public."user" WHERE sha2_hash = ANY(%s)',
            (tester_hashes,)
        )
        print(f"  user 삭제: {cur.rowcount}건")

        # user INSERT
        print("[DB] user INSERT...")
        user_sql = """
            INSERT INTO public."user"
                (sha2_hash, age_grp10, inhome_rate, svod_scrb_cnt_grp,
                 paid_chnl_cnt_grp, ch_hh_avg_month1, kids_use_pv_month1, nfx_use_yn)
            VALUES
                (%(sha2_hash)s, %(age_grp10)s, %(inhome_rate)s, %(svod_scrb_cnt_grp)s,
                 %(paid_chnl_cnt_grp)s, %(ch_hh_avg_month1)s, %(kids_use_pv_month1)s, %(nfx_use_yn)s)
        """
        psycopg2.extras.execute_batch(cur, user_sql, user_records)
        print(f"  {len(user_records)}명 INSERT 완료")

        # watch_history INSERT
        print("[DB] watch_history INSERT...")
        wh_sql = """
            INSERT INTO public.watch_history
                (user_id_fk, vod_id_fk, strt_dt, use_tms, completion_rate, satisfaction)
            VALUES
                (%(user_id_fk)s, %(vod_id_fk)s, %(strt_dt)s, %(use_tms)s,
                 %(completion_rate)s, %(satisfaction)s)
        """
        psycopg2.extras.execute_batch(cur, wh_sql, all_watch_records)
        print(f"  {len(all_watch_records)}건 INSERT 완료")

        conn.commit()
        cur.close()

        print("\n" + "=" * 60)
        print("테스터 계정 생성 완료!")
        print("=" * 60)
        print("\n[다음 단계]")
        print("  1. CF_Engine train.py 재실행 (테스터 유저 추천 생성)")
        print("  2. Hybrid_Layer Phase 1~4 재실행")
        print("\n[테스터 sha2_hash 목록]")
        for tester, ur in zip(TESTERS, user_records):
            print(f"  {tester['label']:20s} → {ur['sha2_hash']}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
