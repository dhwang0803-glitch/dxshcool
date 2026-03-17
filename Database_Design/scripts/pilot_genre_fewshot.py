"""
TV 연예/오락 세부장르 분류 — Few-shot 파일럿

분류 전략:
  1단계 — 안전 키워드 규칙
  2단계 — Few-shot Ollama (레이블링된 예시 활용)

실행:
    python Database_Design/scripts/pilot_genre_fewshot.py           # 신규 100건
    python Database_Design/scripts/pilot_genre_fewshot.py --limit 100
    python Database_Design/scripts/pilot_genre_fewshot.py --rerun   # 기존 300건 재분류
"""
import sys, os, csv, json, argparse, requests, logging
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
LABEL_PATHS  = [
    os.path.join(_root, "Database_Design", "data", "pilot_genre_100_label.csv"),
    os.path.join(_root, "Database_Design", "data", "pilot_genre_fewshot_label.csv"),
    os.path.join(_root, "Database_Design", "data", "pilot_genre_rerun300.csv"),
]
ALL_DATA_PATHS = LABEL_PATHS + [
    os.path.join(_root, "Database_Design", "data", "pilot_genre_fewshot2.csv"),
]
OUT_PATH      = os.path.join(_root, "Database_Design", "data", "pilot_genre_fewshot2.csv")
RERUN_OUT_PATH = os.path.join(_root, "Database_Design", "data", "pilot_genre_rerun300.csv")

GENRES = ["여행", "음식_먹방", "뷰티", "패션", "쇼핑",
          "음악_예능", "연애_데이팅", "버라이어티", "기타"]

VALID_GENRES = set(GENRES) - {"기타"}

# 구 레이블 → 신 레이블 매핑 (기존 label CSV 호환)
GENRE_REMAP = {
    "토크_버라이어티": "버라이어티",
    "체험_버라이어티": "버라이어티",
    "관찰_리얼리티":   "버라이어티",
}

# ── 안전 키워드 ──────────────────────────────────────────────────────────
TRAVEL_SAFE_KEYWORDS = [
    "투어", "세계여행", "배낭",
    "세계일주", "해외여행",
]
TRAVEL_AMBIGUOUS_KEYWORDS = [
    "여행", "해외",
    "나라", "세계", "도시", "글로벌", "미국", "이국", "여정", "탐방",
]
# 다른 장르에서도 오인식이 잦은 모호 키워드 → Ollama 위임
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


# ── Few-shot 예시 로드 (장르당 최대 3건) ────────────────────────────────
def load_fewshot_examples(max_per_genre: int = 3) -> dict[str, list[dict]]:
    examples = {g: [] for g in GENRES if g != "기타"}
    for label_path in LABEL_PATHS:
        with open(label_path, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                # correct_genre 우선, 없으면 genre 컬럼 (rerun300 호환)
                g = row.get('correct_genre') or row.get('genre', '')
                g = g.strip()
                g = GENRE_REMAP.get(g, g)  # 구 레이블 → 버라이어티 매핑
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


# ── Ollama 분류 ──────────────────────────────────────────────────────────
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
        smry=smry,  # 전체 smry 사용 (맥락 최대화)
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


# ── DB 조회 ──────────────────────────────────────────────────────────────
def fetch_excluded_series() -> set[str]:
    excluded = set()
    for label_path in LABEL_PATHS:
        with open(label_path, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                excluded.add(row['series_nm'])
    return excluded

def fetch_series(limit: int, excluded: set[str]) -> list[dict]:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT","5432")),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD")
    )
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (series_nm)
                full_asset_id, series_nm, smry
            FROM vod
            WHERE ct_cl = 'TV 연예/오락'
              AND series_nm IS NOT NULL
              AND smry IS NOT NULL AND smry != ''
              AND series_nm != ALL(%s)
            ORDER BY series_nm, full_asset_id
            LIMIT %s
        """, (list(excluded), limit))
        rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "series_nm": r[1], "smry": r[2]} for r in rows]

def fetch_rerun_series() -> list[dict]:
    """기존 300건 전체 재분류용 — ALL_DATA_PATHS에 있는 series_nm만 조회"""
    target = set()
    for path in ALL_DATA_PATHS:
        with open(path, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                target.add(row['series_nm'])
    log.info("재분류 대상 series_nm 수집: %d건", len(target))
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT","5432")),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD")
    )
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (series_nm)
                full_asset_id, series_nm, smry
            FROM vod
            WHERE ct_cl = 'TV 연예/오락'
              AND series_nm IS NOT NULL
              AND smry IS NOT NULL AND smry != ''
              AND series_nm = ANY(%s)
            ORDER BY series_nm, full_asset_id
        """, (list(target),))
        rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "series_nm": r[1], "smry": r[2]} for r in rows]


# ── 메인 ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--fewshot-per-genre", type=int, default=3)
    parser.add_argument("--rerun", action="store_true", help="기존 300건 재분류")
    args = parser.parse_args()

    log.info("Few-shot 예시 로드 중 (장르당 %d건)...", args.fewshot_per_genre)
    examples = load_fewshot_examples(args.fewshot_per_genre)
    fewshot_block = build_fewshot_block(examples)
    total_examples = sum(len(v) for v in examples.values())
    log.info("Few-shot 예시 총 %d건 로드 완료", total_examples)

    if args.rerun:
        log.info("=== 재분류 모드: 기존 300건 ===")
        series_list = fetch_rerun_series()
        out_path = RERUN_OUT_PATH
    else:
        excluded = fetch_excluded_series()
        log.info("기존 파일럿 제외 목록: %d건", len(excluded))
        log.info("신규 시리즈 %d건 조회 중...", args.limit)
        series_list = fetch_series(args.limit, excluded)
        out_path = OUT_PATH
    log.info("조회 완료: %d건", len(series_list))

    results = []
    kw_count, ol_count, ol_amb_count = 0, 0, 0

    for i, s in enumerate(series_list, 1):
        text = f"{s['series_nm']} {s['smry']}"
        genre, method, matched_kw = keyword_classify(text)

        if genre is None:
            genre = ollama_classify(s["series_nm"], s["smry"], fewshot_block)
            if method == "ollama_ambiguous":
                ol_amb_count += 1
            else:
                ol_count += 1
                method = "ollama"
        else:
            kw_count += 1

        results.append({
            "series_nm": s["series_nm"],
            "genre": genre,
            "method": method,
            "matched_kw": matched_kw,
            "smry_preview": s["smry"][:100].replace("\n", " "),
        })

        log.info("[%d/%d] %-30s → %-15s (%s / kw=%s)",
                 i, len(series_list), s["series_nm"][:30], genre, method, matched_kw or "-")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["series_nm","genre","method","matched_kw","smry_preview"])
        writer.writeheader()
        writer.writerows(results)

    from collections import Counter
    dist = Counter(r["genre"] for r in results)
    log.info("=== 분류 결과 ===")
    log.info("안전키워드: %d건 / Ollama(모호키워드): %d건 / Ollama(키워드없음): %d건",
             kw_count, ol_amb_count, ol_count)
    for g in GENRES:
        log.info("  %-20s: %d건", g, dist.get(g, 0))
    log.info("저장 → %s", out_path)


if __name__ == "__main__":
    main()
