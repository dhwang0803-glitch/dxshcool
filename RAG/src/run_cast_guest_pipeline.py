"""
cast_guest 결측치 채우기 파이프라인
====================================
Stage 1a (TMDB series)   : series_cache.json의 tmdb_id로 credits[4:8] 추출 (비예능)
Stage 1b (TMDB episode)  : TV 연예/오락 에피소드별 guest_stars 추출
                           /tv/{tmdb_id}/season/1/episode/{ep_num}/credits
Stage 2  (smry RAG)      : TV 연예/오락 smry 텍스트에서 게스트명 RAG 추출
Stage 3  (DB UPDATE)     : cast_guest 컬럼 일괄 UPDATE

실행:
    python RAG/src/run_cast_guest_pipeline.py              # 전체
    python RAG/src/run_cast_guest_pipeline.py --stages 12  # Stage 1+2만
    python RAG/src/run_cast_guest_pipeline.py --dry-run    # DB 미반영 확인만
"""

from __future__ import annotations
import json, os, re, sys, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "RAG" / "src"))
load_dotenv(ROOT / ".env")

import requests
import run_approach_b as rab
from validation import validate_cast

BULK_DIR    = ROOT / "RAG" / "data" / "bulk"
CACHE_FILE  = BULK_DIR / "series_cache.json"

CT_VARIETY = "TV 연예/오락"

# ─── 에피소드 번호 추출 ──────────────────────────────────────────────────────

_EP_NUM_KO  = re.compile(r'(\d+)\s*(?:회|화|편)')
_EP_NUM_EN  = re.compile(r'(?:ep|episode)\s*(\d+)', re.IGNORECASE)

def _extract_episode_num(asset_nm: str) -> Optional[int]:
    """asset_nm에서 회차 번호 추출.
    '아는형님 286회' → 286 | '1박2일 ep100' → 100
    """
    m = _EP_NUM_KO.search(asset_nm) or _EP_NUM_EN.search(asset_nm)
    return int(m.group(1)) if m else None


# ─── Stage 1a: 비예능 시리즈 레벨 TMDB credits[4:8] ─────────────────────────

def _fetch_cast_guest_tmdb_series(tmdb_id: int, media_type: str) -> Optional[list]:
    """series_cache tmdb_id로 credits 재조회 → cast[4:8] 추출."""
    try:
        endpoint = "movie" if media_type == "movie" else "tv"
        with rab._sem_tmdb:
            r = requests.get(
                f"{rab._TMDB_URL}/{endpoint}/{tmdb_id}",
                headers=rab._tmdb_headers(),
                params=rab._tmdb_params({"language": "ko-KR",
                                         "append_to_response": "credits"}),
                timeout=10,
            )
        if r.status_code != 200:
            return None
        detail = r.json()
        detail["_media_type"] = media_type
        return rab._extract_cast_guest(detail)
    except Exception:
        return None


def _load_variety_series_nms() -> set:
    """DB에서 TV 연예/오락 series_nm 집합 반환 (Stage 1a 제외 판단용)."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()
    cur.execute(f"SELECT DISTINCT asset_nm FROM vod WHERE ct_cl = '{CT_VARIETY}'")
    asset_nms = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()
    return {rab._series_name(nm) for nm in asset_nms}


def run_stage1a_series_guest(cache: dict) -> dict:
    """비예능 시리즈 레벨 TMDB credits[4:8] 추출.
    Returns: {series_nm: [cast_guest]}
    """
    variety_nms = _load_variety_series_nms()
    todo = {s: d for s, d in cache.items()
            if d.get("tmdb_id") and s not in variety_nms}
    excluded = sum(1 for s in cache if s in variety_nms)
    print(f"\nStage 1a (TMDB series credits[4:8]): {len(todo):,}개 시리즈"
          f" (TV 연예/오락 {excluded:,}개 → Stage 1b 에피소드 처리)")

    guest_map: dict = {}
    lock = threading.Lock()

    def _work(item):
        series, d = item
        result = _fetch_cast_guest_tmdb_series(d["tmdb_id"], d.get("media_type", "tv"))
        return series, result

    with ThreadPoolExecutor(max_workers=rab.MAX_WORKERS) as ex:
        futs = {ex.submit(_work, item): item[0] for item in todo.items()}
        for fut in tqdm(as_completed(futs), total=len(futs), desc="TMDB-series-guest",
                        unit="시리즈", dynamic_ncols=True):
            series, result = fut.result()
            if result:
                with lock:
                    guest_map[series] = result

    print(f"  → TMDB 시리즈 cast_guest 수집: {len(guest_map):,}/{len(todo):,}개")
    return guest_map


# ─── Stage 1b: TV 연예/오락 에피소드 레벨 TMDB guest_stars ──────────────────

def _fetch_episode_guest_stars(tmdb_id: int, ep_num: int) -> Optional[list]:
    """TMDB /tv/{id}/season/1/episode/{ep}/credits → guest_stars 추출."""
    try:
        with rab._sem_tmdb:
            r = requests.get(
                f"{rab._TMDB_URL}/tv/{tmdb_id}/season/1/episode/{ep_num}/credits",
                headers=rab._tmdb_headers(),
                params=rab._tmdb_params({"language": "ko-KR"}),
                timeout=10,
            )
        if r.status_code != 200:
            return None
        data = r.json()
        guest_stars = data.get("guest_stars", [])
        names = [g.get("name", "") for g in guest_stars[:8] if g.get("name")]
        # 한국어 이름 우선, 영문 이름도 허용
        valid = [n for n in names if len(n) >= 2]
        return valid if valid else None
    except Exception:
        return None


def run_stage1b_variety_episode_guest(cache: dict) -> dict:
    """TV 연예/오락 에피소드별 TMDB guest_stars 추출.
    각 에피소드의 회차 번호를 TMDB episode number로 사용 (Season 1 기준).
    Returns: {full_asset_id: [guest_names]}
    """
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()
    cur.execute(f"""
        SELECT full_asset_id, asset_nm
        FROM vod
        WHERE ct_cl = '{CT_VARIETY}'
          AND cast_guest IS NULL
        ORDER BY full_asset_id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    print(f"\nStage 1b (TMDB episode guest_stars): TV 연예/오락 {len(rows):,}건 처리")

    # series_nm → tmdb_id 매핑 (series_cache에서)
    series_tmdb: dict = {}
    for series_nm, d in cache.items():
        if d.get("tmdb_id") and d.get("media_type") != "movie":
            series_tmdb[series_nm] = d["tmdb_id"]

    guest_map: dict = {}   # full_asset_id → [guest_names]
    lock = threading.Lock()
    no_ep_num = 0
    no_tmdb_id = 0

    def _work(row):
        full_asset_id, asset_nm = row
        series_nm = rab._series_name(asset_nm)
        tmdb_id = series_tmdb.get(series_nm)
        if not tmdb_id:
            return full_asset_id, None, "no_tmdb"
        ep_num = _extract_episode_num(asset_nm)
        if not ep_num:
            return full_asset_id, None, "no_ep"
        result = _fetch_episode_guest_stars(tmdb_id, ep_num)
        return full_asset_id, result, "ok"

    with ThreadPoolExecutor(max_workers=rab.MAX_WORKERS) as ex:
        futs = {ex.submit(_work, row): row[0] for row in rows}
        for fut in tqdm(as_completed(futs), total=len(futs), desc="TMDB-episode-guest",
                        unit="건", dynamic_ncols=True):
            full_asset_id, result, status = fut.result()
            if status == "no_ep":
                with lock:
                    no_ep_num += 1
            elif status == "no_tmdb":
                with lock:
                    no_tmdb_id += 1
            elif result:
                with lock:
                    guest_map[full_asset_id] = result

    total = len(rows)
    found = len(guest_map)
    print(f"  → TMDB 에피소드 guest_stars 수집: {found:,}/{total:,} ({found/total*100:.1f}%)")
    print(f"     미매칭: tmdb_id 없음 {no_tmdb_id:,} | 회차번호 없음 {no_ep_num:,}")
    return guest_map


# ─── Stage 2: smry RAG (TV 연예/오락) ──────────────────────────────────────

_GUEST_LABEL = re.compile(
    r'(?:특별\s*)?게스트\s*[:\-]?\s*([가-힣A-Za-z0-9\s,·&X×]+?)(?:[。.!?\n(]|$)'
)
_SPECIAL_APPEAR = re.compile(
    r'특별\s*출연\s*[:\-]?\s*([가-힣]{2,4})'
)
_ROLE_NAME = re.compile(
    r'(?:배우|가수|개그맨|방송인|모델|운동선수|아이돌|MC|래퍼|코미디언|탤런트)'
    r'\s+([가-힣]{2,4})'
)
_NAME_APPEAR = re.compile(
    r'([가-힣]{2,4})(?:이|가)\s+(?:출연|등장|방문|합류|전격\s*합류|특별출연)'
)
_NAME_X_NAME = re.compile(
    r'([가-힣]{2,4})[X×&]\s*([가-힣]{2,4})'
)
_EXPERT_NAME = re.compile(
    r'(?:고수|달인|스타|셰프|요리사)\s+([가-힣]{2,4})'
)
_NAME_JOSA = re.compile(
    r'([가-힣]{2,4})(?:이|가|은|는|의|와|과|도|을|를)\s+'
    r'(?:출연|등장|방문|합류|초대|진행|참여|함께|소개|이야기|준비)'
)

_KO_SURNAMES = {
    '김', '이', '박', '최', '정', '강', '조', '윤', '장', '임',
    '한', '오', '서', '신', '권', '황', '안', '송', '류', '전',
    '홍', '고', '문', '양', '손', '배', '조', '백', '허', '유',
    '남', '심', '노', '하', '곽', '성', '차', '주', '우', '구',
    '신', '임', '나', '전', '민', '유', '진', '지', '엄', '채',
    '원', '천', '방', '공', '현', '함', '변', '염', '여', '추',
    '도', '소', '석', '선', '설', '마', '길', '봉', '시', '형',
}

_STOPWORDS = {
    "오늘", "이번", "지난", "다음", "그날", "매주", "매일", "처음",
    "출연", "게스트", "방송", "특집", "편집", "에피", "시리즈",
    "스튜디오", "무대", "현장", "이야기", "준비", "진행", "특별",
    "연예", "오락", "예능", "드라마", "영화", "프로그램", "리얼리티",
    "여성", "남성", "어린이", "어른", "노인", "청년", "커플",
    "한국", "서울", "부산", "미국", "중국", "일본",
    "음악", "노래", "댄스", "춤", "요리", "여행", "토크",
    "결승", "예선", "미션", "라운드", "시즌",
}

_PARTICLES = re.compile(r'[이가은는을를의도와과에서로]$')


def _extract_guests_from_smry(smry: str) -> list:
    """에피소드 smry 텍스트에서 게스트 인명 추출."""
    raw: list[str] = []

    for m in _GUEST_LABEL.finditer(smry):
        segment = m.group(1)
        parts = re.split(r'[,·\s&X×]+', segment)
        raw.extend(p.strip() for p in parts)

    raw.extend(_SPECIAL_APPEAR.findall(smry))
    raw.extend(_ROLE_NAME.findall(smry))
    raw.extend(_NAME_APPEAR.findall(smry))

    for m in _NAME_X_NAME.finditer(smry):
        raw.extend([m.group(1), m.group(2)])

    raw.extend(_EXPERT_NAME.findall(smry))
    raw.extend(_NAME_JOSA.findall(smry))

    seen: set = set()
    result: list = []
    for n in raw:
        n = n.strip()
        n = _PARTICLES.sub('', n)
        n = _PARTICLES.sub('', n)  # double pass
        if (re.fullmatch(r'[가-힣]{2,4}', n)
                and n not in _STOPWORDS
                and n[0] in _KO_SURNAMES
                and n not in seen):
            seen.add(n)
            result.append(n)

    return result[:8]


def _extract_guests_ollama(smry: str) -> list:
    """Ollama LLM fallback — smry에서 출연자 추출."""
    try:
        prompt = (
            "다음 방송 프로그램 에피소드 소개글에서 출연하는 사람 이름만 추출해줘. "
            "한국어 이름(2~4글자)만, 쉼표로 구분해서 답해줘. "
            "이름이 없으면 '없음'이라고 해줘.\n\n"
            f"소개글: {smry[:300]}\n\n출연자:"
        )
        r = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "exaone3.5:7.8b", "prompt": prompt,
                  "stream": False, "options": {"temperature": 0}},
            timeout=20,
        )
        if r.status_code != 200:
            return []
        text = r.json().get("response", "").strip()
        if "없음" in text:
            return []
        parts = re.split(r'[,，\s]+', text)
        return [p.strip() for p in parts
                if re.fullmatch(r'[가-힣]{2,4}', p.strip())][:8]
    except Exception:
        return []


_sem_ollama = threading.BoundedSemaphore(3)  # Ollama 동시 요청 제한


def run_stage2_smry_guest(max_workers: int = 20) -> dict:
    """TV 연예/오락 smry에서 게스트 추출 (ThreadPoolExecutor 병렬처리).
    Returns: {full_asset_id: [guest_names]}
    """
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()
    cur.execute(f"""
        SELECT full_asset_id, asset_nm, smry
        FROM vod
        WHERE ct_cl = '{CT_VARIETY}'
          AND smry IS NOT NULL AND smry != ''
          AND cast_guest IS NULL
        ORDER BY full_asset_id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    print(f"\nStage 2 (smry RAG): TV 연예/오락 {len(rows):,}건 처리")

    ollama_ok = False
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        ollama_ok = r.status_code == 200
    except Exception:
        pass
    if not ollama_ok:
        print("  ⚠ Ollama 미실행 — regex 전용 모드")

    guest_map: dict = {}
    lock = threading.Lock()
    counters = {"regex": 0, "ollama": 0}

    def _work(row):
        full_asset_id, asset_nm, smry = row
        guests = _extract_guests_from_smry(smry)
        source = "regex"

        if not guests and ollama_ok:
            with _sem_ollama:
                guests = _extract_guests_ollama(smry)
            if guests:
                source = "ollama"

        if guests and validate_cast(guests):
            return full_asset_id, guests, source
        return full_asset_id, None, source

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_work, row): row[0] for row in rows}
        for fut in tqdm(as_completed(futs), total=len(futs), desc="smry-guest",
                        unit="건", dynamic_ncols=True):
            full_asset_id, guests, source = fut.result()
            if guests:
                with lock:
                    guest_map[full_asset_id] = guests
                    counters[source] = counters.get(source, 0) + 1

    total = len(rows)
    found = len(guest_map)
    print(f"  → 게스트 추출 성공: {found:,}/{total:,} ({found/total*100:.1f}%)")
    print(f"     regex: {counters.get('regex',0):,} | ollama: {counters.get('ollama',0):,}")
    return guest_map


# ─── Stage 3: DB UPDATE ────────────────────────────────────────────────────

def _flush_guest_batch(cur, batch: list) -> None:
    for guest_json, source, full_asset_id in batch:
        cur.execute(
            """UPDATE vod
               SET cast_guest = %s,
                   rag_processed = TRUE,
                   rag_source = COALESCE(rag_source || '+' || %s, %s),
                   rag_processed_at = NOW()
               WHERE full_asset_id = %s AND cast_guest IS NULL""",
            (guest_json, source, source, full_asset_id),
        )


def run_stage3_update_db(
    series_guest_map: dict,          # {series_nm: [guests]} — Stage 1a (비예능)
    variety_episode_map: dict,       # {full_asset_id: [guests]} — Stage 1b (TV 연예/오락)
    smry_guest_map: dict,            # {full_asset_id: [guests]} — Stage 2 (smry RAG)
    dry_run: bool = False,
    batch_size: int = 500,
) -> int:
    """cast_guest 컬럼 UPDATE.

    TV 연예/오락:
      - Stage 2(smry) 우선 (에피소드별 정확한 게스트)
      - Stage 1b(TMDB episode guest_stars) fallback
    그 외:
      - Stage 2(smry) 우선
      - Stage 1a(TMDB series credits[4:8]) fallback
    """
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()

    cur.execute("""
        SELECT full_asset_id, asset_nm, ct_cl
        FROM vod WHERE cast_guest IS NULL
        ORDER BY full_asset_id
    """)
    rows = cur.fetchall()
    print(f"\nStage 3 (DB UPDATE): cast_guest NULL {len(rows):,}건 처리")

    batch = []
    updated = 0

    for full_asset_id, asset_nm, ct_cl in tqdm(rows, desc="DB-UPDATE", unit="건",
                                                 dynamic_ncols=True):
        if ct_cl == CT_VARIETY:
            # TV 연예/오락: smry 우선, TMDB 에피소드 fallback
            guests = smry_guest_map.get(full_asset_id)
            source = "smry-RAG"
            if not guests:
                guests = variety_episode_map.get(full_asset_id)
                source = "TMDB-episode"
        else:
            # 비예능: smry 우선, TMDB 시리즈 fallback
            guests = smry_guest_map.get(full_asset_id)
            source = "smry-RAG"
            if not guests:
                series = rab._series_name(asset_nm)
                guests = series_guest_map.get(series)
                source = "TMDB"

        if not guests:
            continue

        guest_json = json.dumps(guests, ensure_ascii=False)
        batch.append((guest_json, source, full_asset_id))

        if len(batch) >= batch_size:
            if not dry_run:
                _flush_guest_batch(cur, batch)
                conn.commit()
            updated += len(batch)
            batch = []

    if batch:
        if not dry_run:
            _flush_guest_batch(cur, batch)
            conn.commit()
        updated += len(batch)

    cur.close()
    conn.close()

    if dry_run:
        print(f"  [dry-run] UPDATE 예정: {updated:,}건")
    else:
        print(f"  → {updated:,}건 UPDATE 완료")
    return updated


# ─── 메인 ──────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="cast_guest 파이프라인")
    parser.add_argument("--dry-run", action="store_true", help="DB 미반영")
    parser.add_argument("--stages", default="123",
                        help="실행할 Stage 번호 (1=TMDB series+episode, 2=smry RAG, 3=DB UPDATE)")
    args = parser.parse_args()

    print("=" * 60)
    print("cast_guest 파이프라인")
    print(f"  dry-run={args.dry_run} | stages={args.stages}")
    print("=" * 60)

    series_guest_map: dict = {}      # Stage 1a
    variety_episode_map: dict = {}   # Stage 1b
    smry_guest_map: dict = {}        # Stage 2

    # Stage 1: TMDB (1a 비예능 시리즈 + 1b TV 연예/오락 에피소드)
    if "1" in args.stages:
        if not CACHE_FILE.exists():
            print("❌ series_cache.json 없음. run_bulk_pipeline.py 먼저 실행 필요.")
            sys.exit(1)
        with open(CACHE_FILE, encoding="utf-8") as f:
            cache = json.load(f)
        print(f"[series_cache 로드] {len(cache):,}개 시리즈")

        # 1a: 비예능 시리즈 레벨
        series_guest_map = run_stage1a_series_guest(cache)

        # 1b: TV 연예/오락 에피소드 레벨
        variety_episode_map = run_stage1b_variety_episode_guest(cache)

    # Stage 2: smry RAG (TV 연예/오락)
    if "2" in args.stages:
        smry_guest_map = run_stage2_smry_guest()

    # Stage 3: DB UPDATE
    if "3" in args.stages:
        total = run_stage3_update_db(
            series_guest_map, variety_episode_map, smry_guest_map,
            dry_run=args.dry_run,
        )

        if not args.dry_run:
            import psycopg2
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")),
                dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
            )
            cur = conn.cursor()
            cur.execute(f"""
                SELECT
                  COUNT(*) FILTER (WHERE cast_guest IS NOT NULL) AS filled,
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE cast_guest IS NOT NULL AND ct_cl = '{CT_VARIETY}') AS variety_filled,
                  COUNT(*) FILTER (WHERE ct_cl = '{CT_VARIETY}') AS variety_total
                FROM vod
            """)
            r = cur.fetchone()
            cur.close()
            conn.close()
            print("\n" + "=" * 60)
            print("최종 결과")
            print("=" * 60)
            print(f"  cast_guest 전체:   {r[0]:,}/{r[1]:,} ({r[0]/r[1]*100:.1f}%)")
            print(f"  TV 연예/오락:      {r[2]:,}/{r[3]:,} ({r[2]/r[3]*100:.1f}%)")
            print(f"  비예능:            {r[0]-r[2]:,}/{r[1]-r[3]:,} "
                  f"({(r[0]-r[2])/(r[1]-r[3])*100:.1f}%)")


if __name__ == "__main__":
    main()
