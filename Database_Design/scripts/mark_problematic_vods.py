"""Notion 정합성 리포트 기반 — 문제 VOD 에피소드를 SVOD(유료)로 전환.

발표 시 실수로 재생되는 것을 방지하기 위한 임시 조치.
원복 시 이 스크립트의 역방향 UPDATE 실행.
"""

import asyncio
import os
import sys

import asyncpg
from dotenv import load_dotenv

load_dotenv()

# ── 문제 에피소드 목록 (Notion 리포트 기반) ──────────────────────────
# key: DB series_nm (LIKE 매칭), value: 회차 번호 리스트 (빈 리스트 = 전체)

PROBLEMATIC_EPISODES: dict[str, list[int]] = {
    "런닝맨": [594, 597, 600, 601, 624],
    "1박2일 시즌4": [
        109, 112, 115, 116, 117, 119,
        125, 126, 127, 129, 130, 131, 132,
        134, 135, 136, 137, 138, 140, 141, 143,
        144, 145, 148, 149, 150, 151, 152,
    ],
    "살림하는 남자들": [
        228, 229, 230, 234, 235, 236, 237,
        242, 244, 245, 249, 250, 251, 252, 253, 254,
        255, 256, 257, 258, 259, 260, 261, 262, 263,
        264, 265, 266, 267, 268, 269, 270, 271, 272,
        273, 274, 275, 276, 277, 278, 279, 280, 281,
    ],
    "오버 더 톱": [1, 2, 3, 4, 5, 6, 8, 9, 10],
    "미스토리 클럽": [2],
    "아는 형님": [
        70, 299, 300, 301, 302, 303, 304, 305,
        311, 313, 314, 315, 317, 318,
    ],
    "그림자 살인": [],  # 영화 — 전체 대상
    "결혼작사 이혼작곡": [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12],
    "뭉쳐야 찬다": [
        15, 18, 20, 22, 23, 24, 25, 26, 27, 28, 29, 30,
        31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 43,
        44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
        56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67,
        68, 69, 70, 71, 74,
    ],
    "뭉쳐야 쏜다": [23, 24],
    "전설체전": [1, 2, 3, 4],
    "공룡대탐험": [1],
    "오은영 리포트 - 결혼지옥": [
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
        13, 14, 15, 16, 17, 18, 20, 21,
    ],
}


async def main():
    sys.stdout.reconfigure(encoding="utf-8")

    conn = await asyncpg.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
    )

    total = 0
    not_found = []

    for series, episodes in PROBLEMATIC_EPISODES.items():
        if not episodes:
            # 영화: series_nm 전체 대상
            result = await conn.execute(
                "UPDATE public.vod SET asset_prod = 'SVOD' "
                "WHERE series_nm = $1 AND asset_prod NOT IN ('SVOD', 'RVOD')",
                series,
            )
            cnt = int(result.split()[-1])
            if cnt:
                print(f"  {series} (전체): {cnt}건 전환")
            total += cnt
            continue

        for ep_num in episodes:
            # 회차 패턴: "594회", "0594회", "594 회" 등 — LIKE '%NNN회%' 로 매칭
            # 0패딩 2자리/3자리 모두 시도
            patterns = [f"%{ep_num:d}회%"]
            if ep_num < 100:
                patterns.append(f"%{ep_num:02d}회%")
            if ep_num < 1000:
                patterns.append(f"%{ep_num:03d}회%")

            matched = False
            for pat in patterns:
                result = await conn.execute(
                    "UPDATE public.vod SET asset_prod = 'SVOD' "
                    "WHERE series_nm = $1 AND asset_nm LIKE $2 "
                    "AND asset_prod NOT IN ('SVOD', 'RVOD')",
                    series, pat,
                )
                cnt = int(result.split()[-1])
                if cnt:
                    print(f"  {series} {ep_num}회: {cnt}건 전환")
                    total += cnt
                    matched = True
                    break

            if not matched:
                # 이미 SVOD/RVOD인지 확인
                existing = await conn.fetchval(
                    "SELECT count(*) FROM public.vod "
                    "WHERE series_nm = $1 AND asset_nm LIKE $2",
                    series, f"%{ep_num}회%",
                )
                if not existing and ep_num < 100:
                    existing = await conn.fetchval(
                        "SELECT count(*) FROM public.vod "
                        "WHERE series_nm = $1 AND asset_nm LIKE $2",
                        series, f"%{ep_num:02d}회%",
                    )
                if existing:
                    print(f"  {series} {ep_num}회: 이미 유료 (skip)")
                else:
                    not_found.append(f"{series} {ep_num}회")

    print(f"\n총 {total}건 SVOD로 전환 완료")

    if not_found:
        print(f"\n매칭 실패 ({len(not_found)}건):")
        for nf in not_found:
            print(f"  - {nf}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
