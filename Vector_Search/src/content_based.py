import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "config" / "search_config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def get_similar_by_meta(vod_id: str, conn, top_n: int = None) -> list[dict]:
    """
    메타데이터 벡터 기반 유사 VOD TOP-N 반환.
    반환: [{"vod_id": str, "content_score": float}, ...]
    """
    config = load_config()
    if top_n is None:
        top_n = config["ensemble"]["top_n"]
    probes = config["search"]["meta_ivfflat_probes"]

    cur = conn.cursor()

    cur.execute(
        "SELECT embedding FROM vod_meta_embedding WHERE vod_id_fk = %s",
        (vod_id,)
    )
    row = cur.fetchone()
    if row is None:
        return []

    query_vec = row[0]

    cur.execute("SET ivfflat.probes = %(probes)s", {"probes": probes})
    cur.execute(
        """
        SELECT vod_id_fk,
               1 - (embedding <=> %s::vector) AS content_score
        FROM vod_meta_embedding
        WHERE vod_id_fk != %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (query_vec, vod_id, query_vec, top_n)
    )
    return [{"vod_id": r[0], "content_score": float(r[1])} for r in cur.fetchall()]
