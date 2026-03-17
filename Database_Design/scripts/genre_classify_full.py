"""
TV 연예/오락 전체 세부장르 분류 + DB 적재

전략:
  1. 기존 CSV(파일럿 293건)에서 이미 분류된 결과 재사용
  2. 나머지 미분류 시리즈 → Few-shot Ollama 분류
  3. 전체 결과를 genre_classify_all.csv 저장
  4. UPDATE vod SET genre_detail = ? WHERE series_nm = ? AND ct_cl = 'TV 연예/오락'
     (시리즈 기준 전파 — 같은 series_nm의 모든 에피소드에 적용)

실행:
    python Database_Design/scripts/genre_classify_full.py            # 분류 + DB 적재
    python Database_Design/scripts/genre_classify_full.py --dry-run  # DB 적재 없이 분류만
"""
import sys, os, csv, argparse, requests, logging
sys.stdout.reconfigure(encoding='utf-8')

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _root)
from dotenv import load_dotenv
load_dotenv(os.path.join(_root, ".env"))
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "exaone3.5:7.8b"

# 기존 분류 결과 CSV (재사용)
EXISTING_PATHS = [
    os.path.join(_root, "Database_Design", "data", "pilot_genre_100_label.csv"),
    os.path.join(_root, "Database_Design", "data", "pilot_genre_fewshot_label.csv"),
    os.path.join(_root, "Database_Design", "data", "pilot_genre_rerun300.csv"),
    os.path.join(_root, "Database_Design", "data", "pilot_genre_fewshot2.csv"),
]
# Few-shot 예시 소스
LABEL_PATHS = [
    os.path.join(_root, "Database_Design", "data", "pilot_genre_100_label.csv"),
    os.path.join(_root, "Database_Design", "data", "pilot_genre_fewshot_label.csv"),
    os.path.join(_root, "Database_Design", "data", "pilot_genre_rerun300.csv"),
]
OUT_PATH = os.path.join(_root, "Database_Design", "data", "genre_classify_all.csv")

GENRES = ["여행", "음식_먹방", "뷰티", "패션", "쇼핑",
          "음악_예능", "연애_데이팅", "버라이어티", "기타"]

GENRE_REMAP = {
    "토크_버라이어티": "버라이어티",
    "체험_버라이어티": "버라이어티",
    "관찰_리얼리티":   "버라이어티",
}

# ── 키워드 규칙 ───────────────────────────────────────────────────────────
TRAVEL_SAFE_KEYWORDS = [
    "투어", "세계여행", "배낭",
    "세계일주", "해외여행",
]
TRAVEL_AMBIGUOUS_KEYWORDS = [
    "여행", "해외",
    "나라", "세계", "도시", "글로벌", "미국", "이국", "여정", "탐방",
]
AMBIGUOUS_KEYWORDS = [
    "토크쇼", "미션", "헤어", "로맨스",
]
KEYWORD_RULES = {
    "음식_먹방": [
        "먹방", "맛집", "음식", "요리", "셰프", "식당", "레스토랑",
        "쿡", "푸드", "food", "먹는", "먹어", "한식", "양식",
        "중식", "일식", "디저트", "밥", "이팅",
    ],
    "뷰티": [
        "뷰티", "화장", "메이크업", "makeup", "피부", "미용",
        "beauty", "스킨케어", "네일", "성형", "코스메틱",
    ],
    "패션": [
        "패션", "fashion", "의상", "코디", "ootd",
        "스트리트패션", "런웨이", "브랜드룩", "패셔니스타",
    ],
    "쇼핑": [
        "쇼핑", "shopping", "홈쇼핑", "구매", "구입",
        "판매", "할인", "세일", "추천템",
    ],
    "음악_예능": [
        "오디션", "트로트", "힙합", "랩스타", "가요제", "뮤지션",
        "보컬", "싱어송라이터", "아이돌 오디션", "가요 프로그램",
    ],
    "연애_데이팅": [
        "연애", "데이팅", "소개팅", "짝을 찾",
        "남녀 출연자", "미팅 프로그램",
    ],
    "버라이어티": [
        "서바이벌", "탈출", "체험", "특수부대",
        "밀리터리", "스턴트", "스포츠 버라이어티",
        "패널", "사연", "상담소",
        "관찰",
    ],
}

def keyword_classify(text: str) -> tuple[str | None, str, str]:
    t = text.lower()
    for kw in TRAVEL_SAFE_KEYWORDS:
        if kw in t:
            return "여행", "keyword", kw
    for kw in TRAVEL_AMBIGUOUS_KEYWORDS:
        if kw in t:
            return None, "ollama_ambiguous", kw
    for kw in AMBIGUOUS_KEYWORDS:
        if kw in t:
            return None, "ollama_ambiguous", kw
    for genre, kws in KEYWORD_RULES.items():
        for kw in kws:
            if kw in t:
                return genre, "keyword", kw
    return None, "ollama", ""


# ── Few-shot 예시 ─────────────────────────────────────────────────────────
def load_fewshot_examples(max_per_genre: int = 3) -> dict[str, list[dict]]:
    examples = {g: [] for g in GENRES if g != "기타"}
    for path in LABEL_PATHS:
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                g = row.get('correct_genre') or row.get('genre', '')
                g = g.strip()
                g = GENRE_REMAP.get(g, g)
                if g in examples and len(examples[g]) < max_per_genre:
                    examples[g].append({
                        "series_nm": row['series_nm'],
                        "smry": row['smry_preview'],
                        "genre": g,
                    })
    return examples

def build_fewshot_block(examples: dict[str, list[dict]]) -> str:
    lines = ["[분류 예시]"]
    for g, items in examples.items():
        for item in items:
            smry_short = item['smry'][:80].replace('\n', ' ')
            lines.append(f"제목: {item['series_nm']} / 줄거리: {smry_short} → {item['genre']}")
    return "\n".join(lines)


# ── Ollama ────────────────────────────────────────────────────────────────
PROMPT_TMPL = """\
다음은 TV 예능/오락 프로그램의 정보입니다.
아래 세부장르 중 가장 적합한 **하나만** 선택해서 장르명만 출력하세요. (설명 불필요)

세부장르 목록:
- 여행 (해외·국내 여행, 배낭여행, 현지 생활 체험 등 — 이동/탐험 자체가 주제)
- 음식_먹방 (맛집 탐방, 먹방, 요리, 쿡방, 식당 운영 등 — 음식이 주제)
- 뷰티 (메이크업, 스킨케어, 헤어, 성형, 미용 등)
- 패션 (스타일링, 코디, 의상, 패션쇼 등)
- 쇼핑 (홈쇼핑, 상품 소개, 구매 리뷰 등)
- 음악_예능 (가수 오디션, 가요쇼, 음악 서바이벌, 음악 버라이어티, 음악 토크 등 — 음악이 핵심)
- 연애_데이팅 (남녀 만남, 연애, 소개팅, 짝 찾기, 결혼 등)
- 버라이어티 (패널 토크, 게스트 인터뷰, 미션, 서바이벌, 게임, 도전, 일상 관찰, 가족 리얼리티, 직업 밀착 등 — 예능 버라이어티 전반)
- 기타 (드라마·영화가 잘못 분류된 경우, 또는 위 항목에 해당 없음)

판단 기준:
- 프로그램의 핵심 포맷·목적을 기준으로 선택하세요.
- 여행을 배경으로 하더라도 음식이 주제면 음식_먹방, 음악이 주제면 음악_예능으로 분류하세요.
- 노래·댄스 경연/오디션이면 버라이어티가 아닌 음악_예능입니다.
- 버라이어티는 토크·미션·게임·도전·관찰·리얼리티 등 예능 포맷 전반을 포함합니다.

{fewshot_block}

[분류 대상]
제목: {title}
줄거리: {smry}

세부장르:"""

def ollama_classify(title: str, smry: str, fewshot_block: str) -> str:
    prompt = PROMPT_TMPL.format(
        fewshot_block=fewshot_block,
        title=title[:80],
        smry=smry,
    )
    try:
        r = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL, "prompt": prompt,
            "stream": False, "options": {"temperature": 0.0, "num_predict": 15}
        }, timeout=30)
        raw = r.json().get("response", "").strip()
        for g in GENRES:
            if g in raw:
                return g
        return "기타"
    except Exception as e:
        log.warning("Ollama 오류: %s", e)
        return "기타"


# ── DB 조회 ───────────────────────────────────────────────────────────────
def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD")
    )

def fetch_all_series() -> list[dict]:
    """TV 연예/오락 전체 시리즈 (series_nm 기준 dedup)"""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (series_nm)
                full_asset_id, series_nm, smry
            FROM vod
            WHERE ct_cl = 'TV 연예/오락'
              AND series_nm IS NOT NULL
              AND smry IS NOT NULL AND smry != ''
            ORDER BY series_nm, full_asset_id
        """)
        rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "series_nm": r[1], "smry": r[2]} for r in rows]

def update_db(results: list[dict], dry_run: bool) -> int:
    """genre_detail을 series_nm 기준으로 전파 업데이트"""
    if dry_run:
        log.info("[dry-run] DB 업데이트 스킵")
        return 0
    conn = get_conn()
    updated_rows = 0
    with conn.cursor() as cur:
        for r in results:
            cur.execute("""
                UPDATE vod
                SET genre_detail = %s, updated_at = NOW()
                WHERE series_nm = %s AND ct_cl = 'TV 연예/오락'
            """, (r["genre"], r["series_nm"]))
            updated_rows += cur.rowcount
    conn.commit()
    conn.close()
    return updated_rows


# ── 기존 분류 결과 로드 ────────────────────────────────────────────────────
def load_existing_classifications() -> dict[str, str]:
    """기존 CSV에서 series_nm → genre 매핑 로드 (CT_CL 오분류 제외)"""
    classified = {}
    for path in EXISTING_PATHS:
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                g = row.get('correct_genre') or row.get('genre', '')
                g = g.strip()
                # CT_CL 오분류 표시된 항목 제외
                if 'CT_CL' in g or 'TV 드라마' in g:
                    continue
                g = GENRE_REMAP.get(g, g)
                if g in set(GENRES):
                    classified[row['series_nm']] = g
    return classified


# ── 메인 ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="DB 적재 없이 분류만 실행")
    parser.add_argument("--fewshot-per-genre", type=int, default=3)
    args = parser.parse_args()

    # 1. Few-shot 예시 로드
    log.info("Few-shot 예시 로드 중...")
    examples = load_fewshot_examples(args.fewshot_per_genre)
    fewshot_block = build_fewshot_block(examples)
    log.info("Few-shot 예시 %d건 로드 완료", sum(len(v) for v in examples.values()))

    # 2. 기존 분류 결과 로드
    existing = load_existing_classifications()
    log.info("기존 분류 재사용: %d건", len(existing))

    # 3. 전체 시리즈 조회
    log.info("DB에서 전체 TV 연예/오락 시리즈 조회 중...")
    all_series = fetch_all_series()
    log.info("전체 시리즈: %d건", len(all_series))

    # 4. 미분류 시리즈만 Ollama 분류
    results = []
    kw_count, ol_count, ol_amb_count, reuse_count = 0, 0, 0, 0

    for i, s in enumerate(all_series, 1):
        nm = s["series_nm"]

        # 기존 분류 재사용
        if nm in existing:
            results.append({
                "series_nm": nm,
                "genre": existing[nm],
                "method": "reuse",
                "matched_kw": "",
                "smry_preview": s["smry"][:100].replace("\n", " "),
            })
            reuse_count += 1
            continue

        # 신규 분류
        text = f"{nm} {s['smry']}"
        genre, method, matched_kw = keyword_classify(text)

        if genre is None:
            genre = ollama_classify(nm, s["smry"], fewshot_block)
            if method == "ollama_ambiguous":
                ol_amb_count += 1
            else:
                ol_count += 1
                method = "ollama"
        else:
            kw_count += 1

        results.append({
            "series_nm": nm,
            "genre": genre,
            "method": method,
            "matched_kw": matched_kw,
            "smry_preview": s["smry"][:100].replace("\n", " "),
        })
        log.info("[%d/%d] %-30s → %-15s (%s / kw=%s)",
                 i, len(all_series), nm[:30], genre, method, matched_kw or "-")

    # 5. CSV 저장
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["series_nm", "genre", "method", "matched_kw", "smry_preview"])
        writer.writeheader()
        writer.writerows(results)
    log.info("CSV 저장 → %s", OUT_PATH)

    # 6. DB 업데이트
    updated_rows = update_db(results, args.dry_run)

    # 7. 요약
    from collections import Counter
    dist = Counter(r["genre"] for r in results)
    log.info("=== 분류 결과 ===")
    log.info("재사용: %d건 / 안전키워드: %d건 / Ollama(모호): %d건 / Ollama: %d건",
             reuse_count, kw_count, ol_amb_count, ol_count)
    for g in GENRES:
        log.info("  %-20s: %d건", g, dist.get(g, 0))
    if not args.dry_run:
        log.info("DB 업데이트 완료: %d행 (genre_detail 전파)", updated_rows)


if __name__ == "__main__":
    main()
