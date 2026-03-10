"""
cast_guest 결측치 채우기 파이프라인
====================================
Stage 1 (TMDB)   : series_cache.json의 tmdb_id를 재활용해 credits[4:8] 추출
Stage 2 (smry)   : TV 연예/오락 에피소드 smry 텍스트에서 게스트명 RAG 추출
Stage 3 (DB UPD) : cast_guest 컬럼 일괄 UPDATE

실행:
    python RAG/src/run_cast_guest_pipeline.py          # 전체
    python RAG/src/run_cast_guest_pipeline.py --dry-run # DB 미반영 확인만
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
GUEST_JSONL = BULK_DIR / "cast_guest_results.jsonl"

# ─── Stage 1: TMDB credits[4:8] ───────────────────────────────────────────

def _fetch_cast_guest_tmdb(series: str, tmdb_id: int, media_type: str) -> Optional[list]:
    """series_cache에 저장된 tmdb_id로 detail 재조회 → cast_guest 추출."""
    try:
        endpoint = "movie" if media_type == "movie" else "tv"
        with rab._sem_tmdb:
            r = requests.get(
                f"{rab._TMDB_URL}/{endpoint}/{tmdb_id}",
                params={"api_key": rab._TMDB_KEY, "language": "ko-KR",
                        "append_to_response": "credits"},
                timeout=10,
            )
        if r.status_code != 200:
            return None
        detail = r.json()
        detail["_media_type"] = media_type
        return rab._extract_cast_guest(detail)
    except Exception:
        return None


def _load_variety_series() -> set:
    """DB에서 TV 연예/오락 시리즈명 목록 로드 — Stage 1 제외 대상."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT asset_nm FROM vod WHERE ct_cl = 'TV 연예/오락'")
    asset_nms = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()
    # asset_nm → series_nm 변환 (run_approach_b._series_name 사용)
    return {rab._series_name(nm) for nm in asset_nms}


def run_stage1_tmdb_guest(cache: dict) -> dict:
    """series_cache의 tmdb_id가 있는 시리즈에서 cast_guest 추출.
    TV 연예/오락은 에피소드별 게스트가 다르므로 Stage 1 제외 → Stage 2(smry)에서 처리.
    """
    variety_series = _load_variety_series()
    todo = {s: d for s, d in cache.items()
            if d.get("tmdb_id") and s not in variety_series}
    excluded = sum(1 for s in cache if s in variety_series)
    print(f"\nStage 1 (TMDB cast_guest): {len(todo):,}개 시리즈 조회"
          f" (TV 연예/오락 {excluded:,}개 제외 → Stage 2 smry 처리)")

    guest_map: dict = {}
    lock = threading.Lock()

    def _work(item):
        series, d = item
        result = _fetch_cast_guest_tmdb(series, d["tmdb_id"], d.get("media_type", "tv"))
        return series, result

    with ThreadPoolExecutor(max_workers=rab.MAX_WORKERS) as ex:
        futs = {ex.submit(_work, item): item[0] for item in todo.items()}
        for fut in tqdm(as_completed(futs), total=len(futs), desc="TMDB-guest",
                        unit="시리즈", dynamic_ncols=True):
            series, result = fut.result()
            if result:
                with lock:
                    guest_map[series] = result

    print(f"  → TMDB cast_guest 수집: {len(guest_map):,}개 시리즈")
    return guest_map


# ─── Stage 2: smry RAG (TV 연예/오락) ──────────────────────────────────────

# ── 한국 인명 추출 패턴 ──────────────────────────────────────────────────

# "게스트: A, B" / "특별게스트 A, B" 라벨 패턴
_GUEST_LABEL = re.compile(
    r'(?:특별\s*)?게스트\s*[:\-]?\s*([가-힣A-Za-z0-9\s,·&X×]+?)(?:[。.!?\n(]|$)'
)
# "특별 출연: A" / "특별출연 A가"
_SPECIAL_APPEAR = re.compile(
    r'특별\s*출연\s*[:\-]?\s*([가-힣]{2,4})'
)
# "배우/가수/개그맨/MC 이름" 직업+이름 패턴
_ROLE_NAME = re.compile(
    r'(?:배우|가수|개그맨|방송인|모델|운동선수|아이돌|MC|래퍼|코미디언|탤런트)'
    r'\s+([가-힣]{2,4})'
)
# "이름이/가 출연/등장/합류" 패턴
_NAME_APPEAR = re.compile(
    r'([가-힣]{2,4})(?:이|가)\s+(?:출연|등장|방문|합류|전격\s*합류|특별출연)'
)
# "이름 X 이름" 커플/매칭 패턴 (예: 양희경X이호균)
_NAME_X_NAME = re.compile(
    r'([가-힣]{2,4})[X×&]\s*([가-힣]{2,4})'
)
# "숨은 요리고수/달인 이름" 형태
_EXPERT_NAME = re.compile(
    r'(?:고수|달인|스타|셰프|요리사)\s+([가-힣]{2,4})'
)
# 이름 뒤 조사로 이름 인식 (이름이/가/은/는/의/와/과 + 문맥 단어)
_NAME_JOSA = re.compile(
    r'([가-힣]{2,4})(?:이|가|은|는|의|와|과|도|을|를)\s+'
    r'(?:출연|등장|방문|합류|초대|진행|참여|함께|소개|이야기|준비)'
)

# 한국 성씨 첫 글자 (이름이면 높은 확률로 성씨로 시작)
_KO_SURNAMES = {
    '김', '이', '박', '최', '정', '강', '조', '윤', '장', '임',
    '한', '오', '서', '신', '권', '황', '안', '송', '류', '전',
    '홍', '고', '문', '양', '손', '배', '조', '백', '허', '유',
    '남', '심', '노', '하', '곽', '성', '차', '주', '우', '구',
    '신', '임', '나', '전', '민', '유', '진', '지', '엄', '채',
    '원', '천', '방', '공', '현', '함', '변', '염', '여', '추',
    '도', '소', '석', '선', '설', '마', '길', '봉', '시', '형',
}

# 제외 단어 (인명이 아닌 것)
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

def _extract_guests_from_smry(smry: str) -> list:
    """에피소드 설명 텍스트에서 게스트 인명 추출."""
    raw: list[str] = []

    # 1. "게스트: A, B" 라벨 — 쉼표/X/& 구분자로 분리
    for m in _GUEST_LABEL.finditer(smry):
        segment = m.group(1)
        parts = re.split(r'[,·\s&X×]+', segment)
        raw.extend(p.strip() for p in parts)

    # 2. "특별 출연 이름" 패턴
    raw.extend(_SPECIAL_APPEAR.findall(smry))

    # 3. "직업 이름" 패턴 (배우 홍길동, 가수 김철수)
    raw.extend(_ROLE_NAME.findall(smry))

    # 4. "이름이/가 출연/등장/합류" 패턴
    raw.extend(_NAME_APPEAR.findall(smry))

    # 5. "이름X이름" 커플/매칭 패턴
    for m in _NAME_X_NAME.finditer(smry):
        raw.extend([m.group(1), m.group(2)])

    # 6. "고수/달인 이름" 패턴
    raw.extend(_EXPERT_NAME.findall(smry))

    # 7. "이름이/가/은/는 + 출연 관련 동사" 패턴
    raw.extend(_NAME_JOSA.findall(smry))

    # 후처리: 조사 제거 + 필터링
    _PARTICLES = re.compile(r'[이가은는을를의도와과에서로]$')
    _PARTICLES2 = re.compile(r'[이가은는을를의도와과에서로]{1,2}$')
    seen: set = set()
    result: list = []
    for n in raw:
        n = n.strip()
        # 조사 제거 (2회 시도: "이효리를" → "이효리" → 그대로)
        n = _PARTICLES.sub('', n)
        n = _PARTICLES.sub('', n)  # double pass (e.g., "이름에서" → "이름에" → "이름")
        if (re.fullmatch(r'[가-힣]{2,4}', n)
                and n not in _STOPWORDS
                and n[0] in _KO_SURNAMES  # 성씨로 시작해야 인명
                and n not in seen):
            seen.add(n)
            result.append(n)

    return result[:8]  # 최대 8명


def _extract_guests_ollama(smry: str) -> list:
    """Ollama LLM fallback — 텍스트에서 출연자 추출."""
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


def run_stage2_smry_guest(dry_run: bool = False) -> dict:
    """TV 연예/오락 smry에서 게스트 추출."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()
    # smry 있고 cast_guest 없는 TV 연예/오락
    cur.execute("""
        SELECT full_asset_id, asset_nm, smry
        FROM vod
        WHERE ct_cl = 'TV 연예/오락'
          AND smry IS NOT NULL AND smry != ''
          AND cast_guest IS NULL
        ORDER BY full_asset_id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    print(f"\nStage 2 (smry RAG): TV 연예/오락 {len(rows):,}건 처리")

    guest_map: dict = {}   # full_asset_id → guest_list
    ollama_fallback = 0
    regex_success = 0

    # Ollama 가동 여부 확인
    ollama_ok = False
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        ollama_ok = r.status_code == 200
    except Exception:
        pass
    if not ollama_ok:
        print("  ⚠ Ollama 미실행 — regex 전용 모드")

    for full_asset_id, asset_nm, smry in tqdm(rows, desc="smry-guest", unit="건",
                                               dynamic_ncols=True):
        guests = _extract_guests_from_smry(smry)

        # regex로 못 찾은 경우 Ollama fallback
        if not guests and ollama_ok:
            guests = _extract_guests_ollama(smry)
            if guests:
                ollama_fallback += 1
        elif guests:
            regex_success += 1

        if guests and validate_cast(guests):
            guest_map[full_asset_id] = guests

    total = len(rows)
    found = len(guest_map)
    print(f"  → 게스트 추출 성공: {found:,}/{total:,} ({found/total*100:.1f}%)")
    print(f"     regex: {regex_success:,} | ollama: {ollama_fallback:,}")
    return guest_map


# ─── Stage 3: DB UPDATE ────────────────────────────────────────────────────

def run_stage3_update_db(
    series_guest_map: dict,   # series_nm → guest_list (Stage 1)
    smry_guest_map: dict,     # full_asset_id → guest_list (Stage 2)
    dry_run: bool = False,
    batch_size: int = 500,
) -> int:
    """cast_guest 컬럼 UPDATE.
    Stage 2(smry) 결과가 Stage 1(TMDB) 결과보다 우선 (예능 특성상 정확도 높음).
    """
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()

    # 전체 rows 조회
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
        # TV 연예/오락: Stage 2(smry) 결과만 사용 — 에피소드별 게스트가 다르므로 시리즈 캐시 사용 금지
        if ct_cl == "TV 연예/오락":
            guests = smry_guest_map.get(full_asset_id)
        else:
            # 그 외: Stage 2(smry) 우선, Stage 1(TMDB) fallback
            guests = smry_guest_map.get(full_asset_id)
            if not guests:
                series = rab._series_name(asset_nm)
                guests = series_guest_map.get(series)

        if not guests:
            continue

        guest_json = json.dumps(guests, ensure_ascii=False)
        source = "smry-RAG" if full_asset_id in smry_guest_map else "TMDB"
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


# ─── 메인 ──────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="cast_guest 파이프라인")
    parser.add_argument("--dry-run", action="store_true", help="DB 미반영")
    parser.add_argument("--stages", default="123", help="실행할 Stage 번호 (예: 12, 3)")
    args = parser.parse_args()

    print("=" * 60)
    print("cast_guest 파이프라인")
    print(f"  dry-run={args.dry_run} | stages={args.stages}")
    print("=" * 60)

    series_guest_map: dict = {}
    smry_guest_map: dict = {}

    # Stage 1: TMDB credits[4:8]
    if "1" in args.stages:
        if not CACHE_FILE.exists():
            print("❌ series_cache.json 없음. run_bulk_pipeline.py 먼저 실행 필요.")
            sys.exit(1)
        with open(CACHE_FILE, encoding="utf-8") as f:
            cache = json.load(f)
        print(f"[series_cache 로드] {len(cache):,}개 시리즈")
        series_guest_map = run_stage1_tmdb_guest(cache)

    # Stage 2: smry RAG (TV 연예/오락)
    if "2" in args.stages:
        smry_guest_map = run_stage2_smry_guest(dry_run=args.dry_run)

    # Stage 3: DB UPDATE
    if "3" in args.stages:
        total = run_stage3_update_db(
            series_guest_map, smry_guest_map, dry_run=args.dry_run
        )

        if not args.dry_run:
            # 최종 검증
            import psycopg2
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")),
                dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
            )
            cur = conn.cursor()
            cur.execute("""
                SELECT
                  COUNT(*) FILTER (WHERE cast_guest IS NOT NULL) AS filled,
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE cast_guest IS NOT NULL AND ct_cl = 'TV 연예/오락') AS variety_filled,
                  COUNT(*) FILTER (WHERE ct_cl = 'TV 연예/오락') AS variety_total
                FROM vod
            """)
            r = cur.fetchone()
            cur.close()
            conn.close()
            print("\n" + "=" * 60)
            print("최종 결과")
            print("=" * 60)
            print(f"  cast_guest 전체: {r[0]:,}/{r[1]:,} ({r[0]/r[1]*100:.1f}%)")
            print(f"  TV 연예/오락:    {r[2]:,}/{r[3]:,} ({r[2]/r[3]*100:.1f}%)")


if __name__ == "__main__":
    main()
