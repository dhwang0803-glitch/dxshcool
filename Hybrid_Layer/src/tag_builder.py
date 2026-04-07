"""Phase 1: VOD 메타데이터에서 해석 가능 태그 추출.

public.vod → public.vod_tag
태그 카테고리: director, actor_lead, actor_guest, genre, genre_detail

confidence 계산:
    log(vote_count+1) / log(MAX_VOTE_COUNT+1) × vote_average/10
    - vote_count, vote_average 없으면 DEFAULT_CONFIDENCE(0.1) 사용
    - 장르/감독/배우 태그 모두 동일 공식 적용
    → 인기+품질 기반으로 장르 내 VOD 정렬 순서 결정
"""

import json
import logging
import math

from Hybrid_Layer.src.base import HybridBase

log = logging.getLogger(__name__)

# tmdb_vote_count max=39,140 기준 (DB 실측값)
_MAX_VOTE_COUNT = 40000
_DEFAULT_CONFIDENCE = 0.1  # TMDB 데이터 없는 VOD (25.6%)

# genre_detail 필터링: 채널/패키지명 등 장르가 아닌 값 제거
_GENRE_DETAIL_BLACKLIST = frozenset({
    # 채널/패키지명
    "무비n시리즈", "만화동산", "제이박스", "게임애니팩토리",
    "캐치온디맨드", "캐치온라이트", "핑크퐁TV", "EBS키즈",
    "투니버스월정액", "IHQ무제한", "MBCevery1", "MBN", "TV조선",
    "KBSN", "채널A", "중화TV", "캐리TV", "BBC키즈", "아이들나라",
    "tvN드라마", "JTBC시사교양", "JTBC드라마", "JTBC4",
    "지상파구작", "레드무비", "테마영화관", "PLAYY영화",
    "양천 사랑방", "케이블 연예오락",
    # 방송사 구작
    "MBC구작", "SBS구작", "KBS구작", "CJENM구작", "JTBC구작",
    # 무의미/분류불가
    "정보미상", "무료영화", "기타", "추천시리즈", "시리즈",
    "동요-동화", "영어-놀이학습", "뮤직비디오",
})

# genre 표기 정규화 (DB 원본에 동일 장르가 다른 표기로 혼재)
_GENRE_NORMALIZE = {
    "연예오락": "연예/오락",
}


class TagBuilder(HybridBase):
    """Phase 1: VOD 메타데이터 → vod_tag 태그 추출 + 적재."""

    @staticmethod
    def _calc_confidence(vote_count, vote_average) -> float:
        """TMDB 투표수 × 평점 기반 confidence 계산 (0~1)."""
        if not vote_count or not vote_average:
            return _DEFAULT_CONFIDENCE
        popularity = math.log(vote_count + 1) / math.log(_MAX_VOTE_COUNT + 1)
        quality = float(vote_average) / 10.0
        return round(min(popularity * quality, 1.0), 6)

    @staticmethod
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

    @staticmethod
    def parse_director(raw: str | None) -> list[str]:
        """쉼표 구분 감독명 파싱. 예: 'Lee Jae-jin, 김형민'"""
        if not raw or not raw.strip():
            return []
        return [d.strip() for d in raw.split(",") if d.strip()]

    @staticmethod
    def parse_genre_detail(raw: str | None) -> list[str]:
        """genre_detail 정제: 채널명 필터링 + TMDB 복합 장르 분리."""
        if not raw or not raw.strip():
            return []
        raw = raw.strip()

        if raw.startswith("(HD)"):
            return []

        if raw in _GENRE_DETAIL_BLACKLIST:
            return []

        parts = [p.strip() for p in raw.replace(", ", ",").split(",") if p.strip()]
        return parts

    @staticmethod
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

    @staticmethod
    def extract_tags_from_row(row: dict) -> list[tuple[str, str, str, float]]:
        """단일 VOD 행에서 (vod_id, tag_category, tag_value, confidence) 리스트 반환."""
        vod_id = row["full_asset_id"]
        conf = TagBuilder._calc_confidence(
            row.get("tmdb_vote_count"), row.get("tmdb_vote_average")
        )
        tags = []

        for d in TagBuilder.parse_director(row.get("director")):
            tags.append((vod_id, "director", d, conf))

        for name in TagBuilder.parse_cast(row.get("cast_lead")):
            tags.append((vod_id, "actor_lead", name, conf))

        for name in TagBuilder.parse_cast(row.get("cast_guest")):
            tags.append((vod_id, "actor_guest", name, conf))

        genre = row.get("genre")
        if genre and genre.strip():
            g = _GENRE_NORMALIZE.get(genre.strip(), genre.strip())
            tags.append((vod_id, "genre", g, conf))

        for gd in TagBuilder.parse_genre_detail(row.get("genre_detail")):
            tags.append((vod_id, "genre_detail", gd, conf))

        return tags

    def build(self, conn) -> int:
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
            all_tags.extend(self.extract_tags_from_row(row))

        log.info("Extracted %d tags, inserting into vod_tag...", len(all_tags))

        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE public.vod_tag")

        inserted = self.batch_upsert(
            conn,
            sql_template="""
                INSERT INTO public.vod_tag (vod_id_fk, tag_category, tag_value, confidence)
                VALUES {args}
                ON CONFLICT DO NOTHING
            """,
            rows=all_tags,
            format_str="(%s,%s,%s,%s)",
            batch_size=5000,
            commit_per_batch=False,
        )
        conn.commit()

        log.info("Inserted %d new tags", inserted)
        return inserted


# ── 모듈 레벨 싱글턴 + 하위 호환 별칭 ──────────────────────────────────────
tag_builder = TagBuilder()

parse_cast = TagBuilder.parse_cast
parse_director = TagBuilder.parse_director
parse_genre_detail = TagBuilder.parse_genre_detail
normalize_rating = TagBuilder.normalize_rating
extract_tags_from_row = TagBuilder.extract_tags_from_row
build_vod_tags = tag_builder.build
