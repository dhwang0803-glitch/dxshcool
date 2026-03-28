"""VOD 메타데이터 + CLIP 임베딩 조회 → LLM 입력 컨텍스트 조립.

DB 왕복 계획:
  읽기: vod 메타데이터 dump (1회) + vod_embedding dump (1회)
  쓰기: 없음
  총계: 2회
"""

import logging
import os

import numpy as np
import psycopg2
from dotenv import load_dotenv

load_dotenv(".env")

log = logging.getLogger(__name__)


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def fetch_vod_contexts(
    conn,
    limit: int = None,
    require_embedding: bool = True,
    require_poster: bool = True,
    stratify_by_ct_cl: bool = False,
) -> list[dict]:
    """VOD 메타 + 임베딩을 한 번에 조회 → LLM 입력 컨텍스트 리스트 반환.

    DB 왕복 계획:
      읽기: vod + vod_embedding JOIN dump (1회)
      총계: 1회

    Args:
        limit: 조회할 최대 VOD 수 (None이면 전체)
        require_embedding: True이면 vod_embedding이 있는 VOD만 조회
        require_poster: True이면 poster_url이 있는 VOD만 조회
        stratify_by_ct_cl: True이면 ct_cl(콘텐츠 유형)별 균등 추출

    Returns:
        [{"vod_id": ..., "asset_nm": ..., "genre": ..., "embedding": [...], ...}, ...]
    """
    embedding_join = "JOIN public.vod_embedding ve ON ve.vod_id_fk = v.full_asset_id" if require_embedding else "LEFT JOIN public.vod_embedding ve ON ve.vod_id_fk = v.full_asset_id"
    poster_filter = "AND v.poster_url IS NOT NULL AND v.poster_url != ''" if require_poster else ""

    if stratify_by_ct_cl and limit:
        # ct_cl별 균등 추출: 각 유형에서 limit/n_types 건씩 RANDOM() 샘플링
        target_ct_cls = ["TV드라마", "영화", "TV 연예/오락", "TV애니메이션", "키즈"]
        per_type = max(1, limit // len(target_ct_cls))
        remainder = limit - per_type * len(target_ct_cls)

        all_rows = []
        for i, ct_cl in enumerate(target_ct_cls):
            extra = 1 if i < remainder else 0
            n = per_type + extra
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT
                        v.full_asset_id, v.asset_nm, v.ct_cl, v.genre, v.genre_detail,
                        v.director, v.cast_lead, v.smry, v.rating, ve.embedding
                    FROM public.vod v
                    {embedding_join}
                    WHERE v.smry IS NOT NULL AND v.smry != ''
                      AND v.ct_cl = %s
                      {poster_filter}
                    ORDER BY RANDOM()
                    LIMIT %s
                    """,
                    (ct_cl, n),
                )
                all_rows.extend(cur.fetchall())
        rows = all_rows
    else:
        limit_clause = f"LIMIT {limit}" if limit else ""
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    v.full_asset_id,
                    v.asset_nm,
                    v.ct_cl,
                    v.genre,
                    v.genre_detail,
                    v.director,
                    v.cast_lead,
                    v.smry,
                    v.rating,
                    ve.embedding
                FROM public.vod v
                {embedding_join}
                WHERE v.smry IS NOT NULL
                  AND v.smry != ''
                  {poster_filter}
                ORDER BY v.full_asset_id
                {limit_clause}
                """
            )
            rows = cur.fetchall()

    contexts = []
    for row in rows:
        vod_id, asset_nm, ct_cl, genre, genre_detail, director, cast_lead, smry, rating, embedding = row
        contexts.append({
            "vod_id": vod_id,
            "asset_nm": asset_nm or "",
            "ct_cl": ct_cl or "",
            "genre": genre or "",
            "genre_detail": genre_detail or "",
            "director": director or "",
            "cast_lead": cast_lead or "",
            "smry": smry or "",
            "rating": rating or "",
            "embedding": _parse_embedding(embedding),
        })

    log.info("fetch_vod_contexts: %d VOD 로드 완료", len(contexts))
    return contexts


def fetch_vod_contexts_by_ids(conn, vod_ids: list[str]) -> list[dict]:
    """vod_id 리스트 기반 컨텍스트 조회 (추천 풀 배치 생성용)."""
    if not vod_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT v.full_asset_id, v.asset_nm, v.ct_cl, v.genre, v.genre_detail,
                   v.director, v.cast_lead, v.smry, v.rating, ve.embedding
            FROM public.vod v
            JOIN public.vod_embedding ve ON ve.vod_id_fk = v.full_asset_id
            WHERE v.full_asset_id = ANY(%s)
              AND v.smry IS NOT NULL AND v.smry != ''
            """,
            (vod_ids,),
        )
        rows = cur.fetchall()

    contexts = []
    for row in rows:
        vod_id, asset_nm, ct_cl, genre, genre_detail, director, cast_lead, smry, rating, embedding = row
        contexts.append({
            "vod_id": vod_id,
            "asset_nm": asset_nm or "",
            "ct_cl": ct_cl or "",
            "genre": genre or "",
            "genre_detail": genre_detail or "",
            "director": director or "",
            "cast_lead": cast_lead or "",
            "smry": smry or "",
            "rating": rating or "",
            "embedding": _parse_embedding(embedding),
        })

    log.info("fetch_vod_contexts_by_ids: %d / %d VOD 로드", len(contexts), len(vod_ids))
    return contexts


def build_prompt(ctx: dict, prompt_template: str) -> str:
    """단일 VOD 컨텍스트 → LLM 프롬프트 조립."""
    embedding_preview = ctx["embedding"][:10] if ctx["embedding"] else []
    return prompt_template.format(
        asset_nm=ctx["asset_nm"],
        genre=ctx["genre"],
        genre_detail=ctx["genre_detail"],
        director=ctx["director"],
        cast_lead=ctx["cast_lead"],
        smry=ctx["smry"][:300] if ctx["smry"] else "",  # 줄거리 300자 제한
        rating=ctx["rating"],
        embedding_preview=embedding_preview,
    )


def _parse_embedding(raw) -> list[float]:
    """pgvector → Python float list 변환."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        return [float(x) for x in raw.strip("[]").split(",") if x.strip()]
    try:
        return list(np.array(raw, dtype=float))
    except Exception:
        return []
