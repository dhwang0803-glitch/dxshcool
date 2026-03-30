"""세그먼트별 맞춤 문구 생성 테스트.

1. user_embedding 재조회 → PCA → 클러스터 중심점 계산
2. 클러스터별 centroid-nearest 대표 5명 추출
3. 테스트 VOD 4건 선택 (드라마/액션/예능/키즈 각 1건)
4. VOD × 세그먼트(5개) 조합으로 맞춤 문구 생성 및 비교 출력

Usage:
    python gen_rec_sentence/scripts/test_segment_generation.py
    python gen_rec_sentence/scripts/test_segment_generation.py --dry-run
"""

import argparse
import json
import logging
import sys
import os

import numpy as np
import pandas as pd
import psycopg2.extras
import ollama

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv(".env")

from gen_rec_sentence.src.context_builder import get_conn
from gen_rec_sentence.src.sentence_generator import _parse_json_response
from gen_rec_sentence.src.visual_extractor import VisualExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

_ASSIGNMENTS_PATH = "gen_rec_sentence/data/cluster_assignments.parquet"
_SEGMENTS_PATH = "gen_rec_sentence/data/user_segments.json"
_CURSOR_ITERSIZE = 50_000
_PCA_N_COMPONENTS = 50
_REPR_N = 5

# ── 세그먼트별 페르소나 (프롬프트 주입용) ──────────────────────────────────────
_SEGMENT_PERSONAS = {
    0: "어린이와 함께 시청하는 키즈/애니 팬. 밝고 경쾌한 톤, 모험·신비·우정·성장을 강조.",
    1: "버라이어티·예능을 즐기는 시청자. 유머·공감·에너지·반전 포인트를 강조.",
    2: "액션·범죄·장르물을 즐기는 성인 시청자. 긴장감·아드레날린·반전·날카로운 서사를 강조.",
    3: "가족 단위 시청자. 감동·따뜻함·공감·세대 간 유대를 강조.",
    4: "드라마 감성을 즐기는 주류 시청자. 감정선·캐릭터·관계·몰입감을 강조.",
}

# rating 기준 톤 게이팅
_SAFE_RATINGS = {"전체가", "7세", "7세이상", "전체", "전체관람가", "전체 관람가"}

# ── ct_cl별 적용 세그먼트 매핑 (None = 모든 세그먼트) ───────────────────────────
# 드라마/영화: 취향층별로 다른 각도 어필 가능 → 전 세그먼트
# 예능/오락: 예능 시청자(Cluster 1)한테만 의미 있음
# 키즈/애니: 키즈 시청자(Cluster 0)한테만 생성
# 시사/문화/다큐: 주류 성인 시청자(Cluster 3, 4)에게만
_CT_CL_SEGMENT_MAP: dict[str, list[int] | None] = {
    "TV드라마":       None,   # 전 세그먼트
    "영화":           None,   # 전 세그먼트
    "시사/문화":      [3, 4],
    "TV다큐멘터리":   [3, 4],
    "TV 연예/오락":   [1],
    "TV예능":         [1],
    "키즈":           [0],
    "TV애니메이션":   [0],
}

# ── 테스트 VOD 타겟 ct_cl ─────────────────────────────────────────────────────
_TEST_CT_CLS = {
    "TV드라마":     1,
    "영화":         1,
    "TV 연예/오락": 1,
    "키즈":         1,
}


# ──────────────────────────────────────────────────────────────────────────────
# Step 1: centroid-nearest 대표 유저 추출
# ──────────────────────────────────────────────────────────────────────────────

def find_repr_users(conn, assignments: pd.DataFrame) -> dict[int, list[str]]:
    """각 클러스터 centroid에 가장 가까운 유저 _REPR_N명 반환."""
    from sklearn.decomposition import PCA

    log.info("[1/4] user_embedding 재조회 및 centroid-nearest 추출 중...")

    user_ids, vectors = [], []
    with conn.cursor("repr_cur", cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.itersize = _CURSOR_ITERSIZE
        cur.execute(
            "SELECT user_id_fk, embedding FROM public.user_embedding WHERE vod_count >= 20 ORDER BY user_id_fk"
        )
        for row in cur:
            raw = row["embedding"]
            vec = _parse_vec(raw)
            if vec and len(vec) == 896:
                user_ids.append(row["user_id_fk"])
                vectors.append(vec)

    X = np.array(vectors, dtype=np.float32)
    pca = PCA(n_components=_PCA_N_COMPONENTS, random_state=42)
    X_pca = pca.fit_transform(X)
    log.info("  PCA 완료 shape=%s", X_pca.shape)

    # cluster_id 매핑
    uid_to_cluster = dict(zip(assignments["user_id"], assignments["cluster_id"]))
    labels = np.array([uid_to_cluster.get(uid, -1) for uid in user_ids])

    n_clusters = int(assignments["cluster_id"].max()) + 1
    repr_users: dict[int, list[str]] = {}

    for cid in range(n_clusters):
        mask = labels == cid
        if not mask.any():
            repr_users[cid] = []
            continue
        cluster_X = X_pca[mask]
        cluster_uids = [uid for uid, m in zip(user_ids, mask) if m]

        centroid = cluster_X.mean(axis=0)
        dists = np.linalg.norm(cluster_X - centroid, axis=1)
        top_idx = np.argsort(dists)[:_REPR_N]
        repr_users[cid] = [cluster_uids[i] for i in top_idx]
        log.info("  Cluster %d 대표 유저 %d명 추출 (centroid-nearest)", cid, len(repr_users[cid]))

    return repr_users


def _parse_vec(raw) -> list[float] | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        s = raw.strip().strip("[]")
        try:
            return [float(p) for p in s.split(",") if p.strip()]
        except ValueError:
            return None
    try:
        return list(np.array(raw, dtype=float))
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Step 2: 테스트 VOD 선택
# ──────────────────────────────────────────────────────────────────────────────

def fetch_test_vods(conn) -> list[dict]:
    """ct_cl별 1건씩 RANDOM() 추출 → 총 4건."""
    log.info("[2/4] 테스트 VOD 선택 중...")
    results = []
    for ct_cl in _TEST_CT_CLS:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT v.full_asset_id, v.asset_nm, v.ct_cl, v.genre, v.genre_detail,
                       v.director, v.cast_lead, v.smry, v.rating, ve.embedding
                FROM public.vod v
                JOIN public.vod_embedding ve ON ve.vod_id_fk = v.full_asset_id
                WHERE v.ct_cl = %s
                  AND v.smry IS NOT NULL AND v.smry != ''
                  AND v.poster_url IS NOT NULL AND v.poster_url != ''
                ORDER BY RANDOM()
                LIMIT 1
                """,
                (ct_cl,),
            )
            row = cur.fetchone()
        if row:
            vod_id, asset_nm, ct_cl_v, genre, genre_detail, director, cast_lead, smry, rating, emb = row
            results.append({
                "vod_id": vod_id,
                "asset_nm": asset_nm or "",
                "ct_cl": ct_cl_v or "",
                "genre": genre or "",
                "genre_detail": genre_detail or "",
                "director": director or "",
                "cast_lead": cast_lead or "",
                "smry": smry or "",
                "rating": rating or "",
                "embedding": _parse_vec(emb) or [],
            })
            log.info("  [%s] %s (%s / %s)", ct_cl, asset_nm, genre_detail, rating)
    return results


# ──────────────────────────────────────────────────────────────────────────────
# Step 3: 세그먼트 페르소나 프롬프트 생성
# ──────────────────────────────────────────────────────────────────────────────

_PERSONA_PROMPT_TEMPLATE = """\
당신은 IPTV VOD 서비스의 감성 카피라이터입니다.
아래 VOD 정보를 바탕으로 홈 배너 포스터 하단에 표시할 감성 문구를 작성하세요.

규칙:
- 정확히 2문장 (줄바꿈 1개로 구분)
- 총 20자 이상 80자 이하 (공백 포함)
- 장면·분위기·감정을 시각적으로 묘사 — 줄거리 요약 금지
- [영상 시각 패턴]이 있으면 해당 분위기를 문구에 반드시 반영할 것
- [타겟 시청자]의 취향과 감성 포인트에 맞춰 문구의 톤과 강조점을 조절할 것
- 감독명·배우명이 한국어면 적극 활용, 영문이면 사용하지 말 것
- 제목·회차 번호를 문구 안에 반복 금지
- "~보세요", "~하세요", "~세요" 등 권유·명령형 어미 금지
- "~있습니다", "~합니다", "~됩니다" 등 합쇼체 어미 금지 — 서술형(~다/~네/~지) 또는 명사형 종결
- HTML 태그(<br> 등) 사용 금지
- JSON 형식으로만 응답: {{"rec_sentence": "..."}}

VOD 정보:
- 제목: {asset_nm}
- 장르: {genre_detail}
- 감독: {director}
- 출연: {cast_lead}
- 줄거리: {smry}
- 영상 시각 패턴: {visual_keywords}

타겟 시청자: {persona}
"""


def build_prompt_for_segment(ctx: dict, segment_id: int) -> str:
    """rating 게이팅 적용 + 세그먼트 페르소나 주입."""
    rating = ctx.get("rating", "")
    # 전체가/7세 등 안전 등급은 세그먼트 무관 범용 프롬프트
    if any(r in rating for r in _SAFE_RATINGS):
        persona = "전 연령 가족 시청자. 밝고 따뜻한 톤 유지."
    else:
        persona = _SEGMENT_PERSONAS.get(segment_id, "일반 시청자.")

    visual_kws = ctx.get("visual_keywords", [])
    visual_str = ", ".join(visual_kws) if visual_kws else "정보 없음"

    return _PERSONA_PROMPT_TEMPLATE.format(
        asset_nm=ctx.get("asset_nm", ""),
        genre_detail=ctx.get("genre_detail", ""),
        director=ctx.get("director", ""),
        cast_lead=ctx.get("cast_lead", ""),
        smry=ctx.get("smry", "")[:300],
        visual_keywords=visual_str,
        persona=persona,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Step 4: VOD × 세그먼트 문구 생성
# ──────────────────────────────────────────────────────────────────────────────

def _call_ollama(prompt: str, model: str = "gemma2:9b", temperature: float = 0.7) -> str:
    """이미 완성된 프롬프트를 ollama에 직접 전달 → rec_sentence 문자열 반환."""
    for attempt in range(3):
        try:
            response = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": temperature + attempt * 0.1},
            )
            content = response["message"]["content"].strip()
            parsed = _parse_json_response(content)
            return parsed.get("rec_sentence", "(파싱 실패)")
        except Exception as e:
            log.warning("  ollama 호출 실패 (시도 %d): %s", attempt + 1, e)
    return "(생성 실패)"


def run_generation(
    vods: list[dict],
    segments: list[dict],
    extractor: VisualExtractor,
    dry_run: bool = False,
    temperature: float = 0.7,
) -> list[dict]:
    results = []

    for vod in vods:
        # 시각 키워드 추출
        emb = vod.get("embedding", [])
        visual_keywords = extractor.extract(emb, top_k=5) if emb else []
        vod["visual_keywords"] = visual_keywords

        log.info("\n▶ [%s] %s (%s)", vod["ct_cl"], vod["asset_nm"], vod["rating"])
        if visual_keywords:
            log.info("  시각 키워드: %s", ", ".join(visual_keywords))

        vod_result = {
            "vod_id": vod["vod_id"],
            "asset_nm": vod["asset_nm"],
            "ct_cl": vod["ct_cl"],
            "rating": vod["rating"],
            "visual_keywords": visual_keywords,
            "segments": [],
        }

        # ct_cl별 적용 세그먼트 결정
        allowed = _CT_CL_SEGMENT_MAP.get(vod["ct_cl"])  # None = 전체
        target_segs = [s for s in segments if allowed is None or s["cluster_id"] in allowed]
        skipped = len(segments) - len(target_segs)
        if skipped:
            log.info("  ct_cl=%s → 세그먼트 %d개 생성 (나머지 %d개 스킵)",
                     vod["ct_cl"], len(target_segs), skipped)

        for seg in target_segs:
            cid = seg["cluster_id"]
            label = seg["label"]
            prompt = build_prompt_for_segment(vod, cid)

            if dry_run:
                sentence = f"[DRY-RUN] {label} 세그먼트 문구 미생성"
                log.info("  [Cluster %d / %s] DRY-RUN", cid, label)
            else:
                sentence = _call_ollama(prompt, temperature=temperature)
                log.info("  [Cluster %d / %s] %s", cid, label, sentence[:60])

            vod_result["segments"].append({
                "cluster_id": cid,
                "label": label,
                "sentence": sentence,
            })

        results.append(vod_result)

    return results


# ──────────────────────────────────────────────────────────────────────────────
# 결과 출력
# ──────────────────────────────────────────────────────────────────────────────

def print_results(results: list[dict]) -> None:
    print("\n" + "═" * 70)
    print("  세그먼트별 맞춤 문구 생성 결과")
    print("═" * 70)

    for r in results:
        print(f"\n【 {r['asset_nm']} 】  ct_cl={r['ct_cl']}  rating={r['rating']}")
        print(f"  시각 키워드: {', '.join(r['visual_keywords']) or '없음'}")
        print("  " + "─" * 60)
        for seg in r["segments"]:
            label = seg["label"]
            sent = seg["sentence"]
            print(f"  [{seg['cluster_id']}] {label:<18}  {sent}")
        print()


# ──────────────────────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="세그먼트별 맞춤 문구 생성 테스트")
    parser.add_argument("--dry-run", action="store_true", help="LLM 호출 없이 구조만 확인")
    parser.add_argument("--temperature", type=float, default=0.7)
    args = parser.parse_args()

    # 세그먼트 메타 로드
    with open(_SEGMENTS_PATH, encoding="utf-8") as f:
        segments = json.load(f)

    assignments = pd.read_parquet(_ASSIGNMENTS_PATH)

    conn = get_conn()
    try:
        # 대표 유저 추출
        repr_users = find_repr_users(conn, assignments)
        log.info("[대표 유저 요약]")
        for cid, uids in repr_users.items():
            label = segments[cid]["label"]
            log.info("  Cluster %d (%s): %s ...", cid, label,
                     ", ".join(u[:8] for u in uids[:3]))

        # 테스트 VOD 선택
        vods = fetch_test_vods(conn)
        if not vods:
            log.error("테스트 VOD를 찾을 수 없습니다.")
            return

        log.info("[3/4] VisualExtractor 초기화 중...")
        extractor = VisualExtractor()

        # 문구 생성
        log.info("[4/4] 세그먼트별 문구 생성 중... (VOD %d건 × 세그먼트 %d개)", len(vods), len(segments))
        results = run_generation(vods, segments, extractor, dry_run=args.dry_run, temperature=args.temperature)

    finally:
        conn.close()

    print_results(results)

    # JSON 저장
    out_path = "gen_rec_sentence/data/segment_generation_test.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    log.info("결과 저장: %s", out_path)


if __name__ == "__main__":
    main()
