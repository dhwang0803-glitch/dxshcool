"""rec_sentence 조회 헬퍼.

유저의 segment_id(또는 age_grp10 기반 default)로
serving.rec_sentence에서 VOD별 맞춤 문구를 조회한다.
"""

# age_grp10 → cold-start 기본 segment_id (user_segment 분포 기반)
_AGE_DEFAULT_SEGMENT: dict[str, int] = {
    "10대":    0,   # 키즈/애니
    "20대":    1,   # 예능/버라이어티
    "30대":    1,   # 예능/버라이어티
    "40대":    1,   # 예능/버라이어티
    "50대":    4,   # 메인스트림 드라마
    "60대":    4,   # 메인스트림 드라마
    "70대":    1,   # 예능/버라이어티
    "80대":    1,   # 예능/버라이어티
    "90대이상": 1,  # 예능/버라이어티
}
_FALLBACK_SEGMENT = 4  # segment 정보 전혀 없을 때


async def get_segment_id(conn, user_id: str) -> int:
    """유저의 segment_id 반환.

    우선순위:
      1. user_segment 테이블 (K-Means 클러스터 결과)
      2. user.age_grp10 기반 default
      3. 전체 fallback (segment 4)
    """
    row = await conn.fetchrow(
        "SELECT segment_id FROM public.user_segment WHERE user_id_fk = $1",
        user_id,
    )
    if row:
        return row["segment_id"]

    age_row = await conn.fetchrow(
        "SELECT age_grp10 FROM public.user WHERE sha2_hash = $1",
        user_id,
    )
    if age_row and age_row["age_grp10"]:
        return _AGE_DEFAULT_SEGMENT.get(age_row["age_grp10"], _FALLBACK_SEGMENT)

    return _FALLBACK_SEGMENT


async def get_rec_sentences(conn, vod_ids: list[str], segment_id: int) -> dict[str, str]:
    """vod_id 목록에 대해 주어진 segment_id의 rec_sentence를 bulk 조회.

    Returns:
        {vod_id_fk: rec_sentence} — 없으면 해당 key 미포함
    """
    if not vod_ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT vod_id_fk, rec_sentence
        FROM serving.rec_sentence
        WHERE vod_id_fk = ANY($1) AND segment_id = $2
        """,
        vod_ids,
        segment_id,
    )
    return {r["vod_id_fk"]: r["rec_sentence"] for r in rows}
