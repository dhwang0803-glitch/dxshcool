import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config" / "search_config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_similar_by_meta(vod_id: str, conn, top_n: int = None) -> list[dict]:
    """
    메타데이터 벡터 기반 유사 VOD TOP-N 반환 (시리즈 대표 임베딩 사용).

    vod_series_embedding(시리즈당 1건, ~14.8K)을 검색하여
    에피소드 중복 없이 시리즈 다양성이 보장된 결과를 반환한다.
    반환: [{"vod_id": str, "content_score": float}, ...]
    """
    config = load_config()
    if top_n is None:
        top_n = config["ensemble"]["top_n"]
    probes = config["search"]["series_ivfflat_probes"]

    cur = conn.cursor()

    # 입력 vod_id → 소속 시리즈의 대표 임베딩 조회
    cur.execute(
        """
        SELECT se.embedding, se.series_nm
        FROM vod_series_embedding se
        JOIN vod v ON COALESCE(v.series_nm, v.asset_nm) = se.series_nm
        WHERE v.full_asset_id = %s
        LIMIT 1
        """,
        (vod_id,),
    )
    row = cur.fetchone()
    if row is None:
        return []

    query_vec, source_series = row

    cur.execute("SET ivfflat.probes = %(probes)s", {"probes": probes})
    cur.execute(
        """
        SELECT representative_vod_id,
               1 - (embedding <=> %s::vector) AS content_score
        FROM vod_series_embedding
        WHERE series_nm != %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (query_vec, source_series, query_vec, top_n),
    )
    return [{"vod_id": r[0], "content_score": float(r[1])} for r in cur.fetchall()]
