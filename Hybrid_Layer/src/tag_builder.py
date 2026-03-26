"""Phase 1: VOD 메타데이터에서 해석 가능 태그 추출.

public.vod → public.vod_tag
태그 카테고리: director, actor_lead, actor_guest, genre, genre_detail, rating

confidence 계산:
    log(vote_count+1) / log(MAX_VOTE_COUNT+1) × vote_average/10
    - vote_count, vote_average 없으면 DEFAULT_CONFIDENCE(0.1) 사용
    - 장르/감독/배우 태그 모두 동일 공식 적용
    → 인기+품질 기반으로 장르 내 VOD 정렬 순서 결정
"""

import json
import logging
import math

log = logging.getLogger(__name__)

# tmdb_vote_count max=39,140 기준 (DB 실측값)
_MAX_VOTE_COUNT = 40000
_DEFAULT_CONFIDENCE = 0.1  # TMDB 데이터 없는 VOD (25.6%)


def _calc_confidence(vote_count, vote_average) -> float:
    """TMDB 투표수 × 평점 기반 confidence 계산 (0~1)."""
    if not vote_count or not vote_average:
        return _DEFAULT_CONFIDENCE
    popularity = math.log(vote_count + 1) / math.log(_MAX_VOTE_COUNT + 1)
    quality = float(vote_average) / 10.0
    return round(min(popularity * quality, 1.0), 6)


def parse_cast(raw: str | None) -> list[str]:
    """cast_lead/cast_guest JSON 배열 문자열 파싱. 예: '["최불암", "김혜자"]'"""
    if not raw or not raw.strip():
        return []
    try:
        names = json.loads(raw)
        if isinstance(names, list):
            return [n.strip() for n in names if n and n.strip()]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def parse_director(raw: str | None) -> list[str]:
    """쉼표 구분 감독명 파싱. 예: 'Lee Jae-jin, 김형민'"""
    if not raw or not raw.strip():
        return []
    return [d.strip() for d in raw.split(",") if d.strip()]


def normalize_rating(raw: str | None) -> str | None:
    """등급 정규화: 다양한 형식 → 표준 형식."""
    if not raw or not raw.strip():
        return None
    r = raw.strip()
    mapping = {
        "7": "7세이상관람가",
        "12": "12세이상관람가",
        "12세이상": "12세이상관람가",
        "15": "15세이상관람가",
        "15세이상": "15세이상관람가",
        "19": "청소년관람불가",
    }
    return mapping.get(r, r)


def extract_tags_from_row(row: dict) -> list[tuple[str, str, str, float]]:
    """단일 VOD 행에서 (vod_id, tag_category, tag_value, confidence) 리스트 반환."""
    vod_id = row["full_asset_id"]
    conf = _calc_confidence(row.get("tmdb_vote_count"), row.get("tmdb_vote_average"))
    tags = []

    # director
    for d in parse_director(row.get("director")):
        tags.append((vod_id, "director", d, conf))

    # actor_lead (cast_lead: 주연)
    for name in parse_cast(row.get("cast_lead")):
        tags.append((vod_id, "actor_lead", name, conf))

    # actor_guest (cast_guest: 게스트/조연)
    for name in parse_cast(row.get("cast_guest")):
        tags.append((vod_id, "actor_guest", name, conf))

    # genre
    genre = row.get("genre")
    if genre and genre.strip():
        tags.append((vod_id, "genre", genre.strip(), conf))

    # genre_detail
    genre_detail = row.get("genre_detail")
    if genre_detail and genre_detail.strip():
        tags.append((vod_id, "genre_detail", genre_detail.strip(), conf))

    # rating
    rating = normalize_rating(row.get("rating"))
    if rating:
        tags.append((vod_id, "rating", rating, conf))

    return tags


def build_vod_tags(conn) -> int:
    """전체 VOD에서 태그를 추출하여 vod_tag 테이블에 적재.

    Returns:
        적재된 태그 수
    """
    log.info("Loading VOD metadata...")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT full_asset_id, director, cast_lead, cast_guest,
                   genre, genre_detail, rating,
                   tmdb_vote_count, tmdb_vote_average
            FROM public.vod
            WHERE full_asset_id IS NOT NULL
            """
        )
        columns = [desc[0] for desc in cur.description]
        rows = [dict(zip(columns, r)) for r in cur.fetchall()]

    log.info("Loaded %d VODs, extracting tags...", len(rows))

    all_tags = []
    for row in rows:
        all_tags.extend(extract_tags_from_row(row))

    log.info("Extracted %d tags, inserting into vod_tag...", len(all_tags))

    # 기존 데이터 삭제 후 재적재 (confidence 값 갱신)
    inserted = 0
    batch_size = 5000
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE public.vod_tag")
        for i in range(0, len(all_tags), batch_size):
            batch = all_tags[i: i + batch_size]
            args = ",".join(
                cur.mogrify("(%s,%s,%s,%s)", t).decode() for t in batch
            )
            cur.execute(
                f"""
                INSERT INTO public.vod_tag (vod_id_fk, tag_category, tag_value, confidence)
                VALUES {args}
                ON CONFLICT DO NOTHING
                """
            )
            inserted += cur.rowcount
        conn.commit()

    log.info("Inserted %d new tags", inserted)
    return inserted
