"""Phase 1: VOD 메타데이터에서 해석 가능 태그 추출.

public.vod → public.vod_tag
태그 카테고리: director, actor, genre, genre_detail, rating
"""

import json
import logging

log = logging.getLogger(__name__)


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
    tags = []

    # director
    for d in parse_director(row.get("director")):
        tags.append((vod_id, "director", d, 1.0))

    # actor (cast_lead + cast_guest)
    actors = set()
    for name in parse_cast(row.get("cast_lead")):
        actors.add(name)
    for name in parse_cast(row.get("cast_guest")):
        actors.add(name)
    for a in actors:
        tags.append((vod_id, "actor", a, 1.0))

    # genre
    genre = row.get("genre")
    if genre and genre.strip():
        tags.append((vod_id, "genre", genre.strip(), 1.0))

    # genre_detail
    genre_detail = row.get("genre_detail")
    if genre_detail and genre_detail.strip():
        tags.append((vod_id, "genre_detail", genre_detail.strip(), 1.0))

    # rating
    rating = normalize_rating(row.get("rating"))
    if rating:
        tags.append((vod_id, "rating", rating, 1.0))

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
                   genre, genre_detail, rating
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

    # 배치 INSERT (ON CONFLICT DO NOTHING)
    inserted = 0
    batch_size = 5000
    with conn.cursor() as cur:
        for i in range(0, len(all_tags), batch_size):
            batch = all_tags[i : i + batch_size]
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

    log.info("Inserted %d new tags (skipped duplicates)", inserted)
    return inserted
