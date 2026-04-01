"""
VPC 업로드 완료 후 vod.poster_url 일괄 업데이트 (관리자 전용).
직접 실행 X — scripts/update_poster_url.py에서 import해서 사용.

업데이트 기준: (series_nm, season) 일치
"""
import logging
from typing import Callable

from Poster_Collection.src.base import PosterBase

logger = logging.getLogger(__name__)


class DBUpdater(PosterBase):
    """DB poster_url UPDATE 클래스."""

    @staticmethod
    def update_poster_urls(conn, mapping: dict) -> int:
        """
        series_nm → vpc_url 매핑으로 vod.poster_url 일괄 UPDATE.
        (하위 호환용 — 시즌 구분 없이 series_nm 전체 업데이트)

        Args:
            conn: psycopg2 connection
            mapping: {series_nm: vpc_url}

        Returns:
            총 업데이트된 행 수
        """
        if not mapping:
            logger.warning("매핑이 비어 있습니다. 업데이트를 건너뜁니다.")
            return 0

        total_updated = 0
        with conn.cursor() as cur:
            for series_nm, vpc_url in mapping.items():
                cur.execute(
                    """
                    UPDATE vod
                    SET poster_url = %s,
                        updated_at = NOW()
                    WHERE series_nm = %s
                      AND poster_url IS NULL
                    """,
                    (vpc_url, series_nm),
                )
                rows = cur.rowcount
                total_updated += rows
                if rows:
                    logger.debug("series_nm=%s → %d행 업데이트", series_nm, rows)

        conn.commit()
        logger.info("총 업데이트 행: %d (시리즈: %d건)", total_updated, len(mapping))
        return total_updated

    @staticmethod
    def update_poster_urls_by_season(
        conn,
        season_mapping: dict,
        parse_season_fn: Callable[[str], tuple[str, int]],
    ) -> int:
        """
        (series_nm, season) → url 매핑으로 시즌별 poster_url UPDATE.

        각 VOD의 asset_nm에서 시즌을 파싱하여 해당 시즌의 포스터 URL로 업데이트.

        Args:
            conn: psycopg2 connection
            season_mapping: {(series_nm, season): url}
            parse_season_fn: asset_nm → (base, season) 파싱 함수

        Returns:
            총 업데이트된 행 수
        """
        if not season_mapping:
            logger.warning("시즌 매핑이 비어 있습니다.")
            return 0

        # series_nm별로 그룹핑
        series_urls: dict[str, dict[int, str]] = {}
        for (snm, season), url in season_mapping.items():
            series_urls.setdefault(snm, {})[season] = url

        total_updated = 0
        with conn.cursor() as cur:
            for snm, season_url_map in series_urls.items():
                cur.execute(
                    "SELECT full_asset_id, asset_nm FROM vod WHERE series_nm = %s",
                    (snm,),
                )
                vods = cur.fetchall()

                season_ids: dict[int, list[str]] = {}
                for full_asset_id, asset_nm in vods:
                    _, season = parse_season_fn(asset_nm) if asset_nm else ("", 1)
                    season_ids.setdefault(season, []).append(full_asset_id)

                for season, ids in season_ids.items():
                    url = season_url_map.get(season)
                    if not url:
                        continue
                    cur.execute(
                        """
                        UPDATE vod
                        SET poster_url = %s,
                            updated_at = NOW()
                        WHERE full_asset_id = ANY(%s)
                        """,
                        (url, ids),
                    )
                    total_updated += cur.rowcount

        conn.commit()
        logger.info(
            "시즌별 업데이트 완료: %d행 (시리즈 %d개, 시즌매핑 %d건)",
            total_updated, len(series_urls), len(season_mapping),
        )
        return total_updated


# ── 싱글턴 + 하위호환 별칭 ──
_updater = DBUpdater()

update_poster_urls = DBUpdater.update_poster_urls
update_poster_urls_by_season = DBUpdater.update_poster_urls_by_season
