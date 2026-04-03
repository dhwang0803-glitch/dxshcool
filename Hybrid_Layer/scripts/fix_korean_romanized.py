"""영문 로마자 한국인 이름 → 한글 자동 변환.

성씨 + 이름 음절 규칙 기반 변환.
vod (director, cast_lead, cast_guest) + vod_tag + user_preference 3개 테이블 업데이트.
"""
import sys
import os
import re

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

import psycopg2
from dotenv import load_dotenv

load_dotenv()

# ── 성씨 매핑 ──
SURNAME_MAP = {
    "lee": "이", "kim": "김", "park": "박", "choi": "최", "jung": "정",
    "jeong": "정", "jang": "장", "chang": "장", "cho": "조", "yoo": "유",
    "yu": "유", "yoon": "윤", "yun": "윤", "shin": "신", "han": "한",
    "oh": "오", "seo": "서", "kwon": "권", "hwang": "황", "ahn": "안",
    "an": "안", "song": "송", "jeon": "전", "kang": "강", "bae": "배",
    "lim": "임", "im": "임", "ryu": "류", "moon": "문", "hong": "홍",
    "go": "고", "ko": "고", "min": "민", "baek": "백", "heo": "허",
    "nam": "남", "noh": "노", "ha": "하", "woo": "우", "son": "손",
    "yang": "양", "won": "원", "chun": "천", "byun": "변", "kwak": "곽",
    "gu": "구", "koo": "구", "eom": "엄", "um": "엄", "pyo": "표",
    "ban": "반", "chae": "채", "ji": "지", "do": "도", "sim": "심",
    "ye": "예", "yeh": "예", "nah": "나", "na": "나",
}

# ── 이름 음절 매핑 (자주 쓰이는 것들) ──
SYLLABLE_MAP = {
    # 모음/자음 조합
    "gun": "건", "geun": "근", "gyu": "규", "gi": "기", "guk": "국",
    "gwang": "광", "gwon": "권",
    "na": "나", "nam": "남", "nah": "나",
    "dae": "대", "do": "도", "dong": "동", "deok": "덕", "deuk": "득",
    "ra": "라", "rae": "래", "ri": "리", "rim": "림",
    "man": "만", "mi": "미", "min": "민", "myeong": "명", "myung": "명",
    "moo": "무", "moon": "문", "mun": "문",
    "ba": "바", "bae": "배", "beom": "범", "bo": "보", "bin": "빈",
    "byeong": "병", "byung": "병", "bong": "봉", "bu": "부", "bum": "범",
    "sa": "사", "sang": "상", "seo": "서", "seob": "섭", "seok": "석",
    "seol": "설", "seong": "성", "si": "시", "sik": "식", "soo": "수",
    "su": "수", "sub": "섭", "sob": "섭", "sun": "선", "sung": "성",
    "sul": "슬", "soon": "순",
    "ah": "아", "ak": "악", "an": "안",
    "ya": "야", "yang": "양", "yeon": "연", "yeong": "영", "young": "영",
    "ye": "예", "yong": "용", "yoon": "윤", "yun": "윤",
    "eun": "은", "ui": "의",
    "in": "인", "il": "일",
    "ja": "자", "jae": "재", "jeong": "정", "jong": "종", "joo": "주",
    "ju": "주", "jun": "준", "jung": "정", "jin": "진",
    "chan": "찬", "chang": "창", "cheol": "철", "chul": "철",
    "cheon": "천", "choon": "춘",
    "tae": "태", "tak": "탁",
    "pil": "필",
    "ha": "하", "hae": "해", "han": "한", "hee": "희", "heon": "헌",
    "ho": "호", "hong": "홍", "hwa": "화", "hwan": "환", "hyeok": "혁",
    "hyeon": "현", "hyun": "현", "hyung": "형", "hye": "혜", "hyuk": "혁",
    # 자주 쓰이는 통 음절
    "woo": "우", "wook": "욱", "won": "원", "woong": "웅",
    "gi": "기", "ki": "기", "kyo": "교", "kyung": "경",
    "ok": "옥", "rin": "린", "ram": "람",
    "seon": "선", "hye": "혜",
    "joong": "중", "joon": "준",
    "la": "라", "noo": "누", "sook": "숙", "im": "임",
    "bi": "비",
}


def romanized_to_korean(name: str) -> str | None:
    """영문 로마자 한국인 이름 → 한글 변환. 변환 불가 시 None."""
    # "Na-ri Lee" 형태 (이름-성) 감지
    parts = name.strip().split()
    if len(parts) < 2:
        return None

    # 성이 앞에 오는 경우 (Lee Jang-woo) vs 뒤에 오는 경우 (Na-ri Lee)
    first_lower = parts[0].lower().rstrip(",")
    last_lower = parts[-1].lower()

    if first_lower in SURNAME_MAP:
        surname_kr = SURNAME_MAP[first_lower]
        given_parts = " ".join(parts[1:])
    elif last_lower in SURNAME_MAP:
        surname_kr = SURNAME_MAP[last_lower]
        given_parts = " ".join(parts[:-1])
    else:
        return None

    # 이름 음절 분리 (하이픈 또는 공백)
    syllables = re.split(r"[\-\s]+", given_parts.strip())
    given_kr = ""
    for syl in syllables:
        s = syl.lower().strip()
        if s in SYLLABLE_MAP:
            given_kr += SYLLABLE_MAP[s]
        else:
            return None  # 변환 불가 음절 있으면 포기

    if not given_kr:
        return None

    return surname_kr + given_kr


def main():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()

    # 영문 로마자 한국인 이름 후보 조회
    cur.execute("""
        SELECT DISTINCT tag_value
        FROM public.user_preference
        WHERE tag_category IN ('director', 'actor_lead', 'actor_guest')
          AND tag_value ~ E'^[A-Za-z \\-\\.\\,\\']+$'
    """)

    candidates = [row[0] for row in cur.fetchall()]
    print(f"영문 이름 후보: {len(candidates):,}개", flush=True)

    converted = {}
    for name in candidates:
        kr = romanized_to_korean(name)
        if kr:
            converted[name] = kr

    print(f"변환 가능: {len(converted):,}개", flush=True)

    vod_total = 0
    tag_total = 0
    pref_total = 0

    for i, (old_name, new_name) in enumerate(converted.items(), 1):
        # 1. vod
        for col in ("director", "cast_lead", "cast_guest"):
            cur.execute(
                f"UPDATE public.vod SET {col} = REPLACE({col}, %s, %s) WHERE {col} LIKE %s",
                (old_name, new_name, f"%{old_name}%"),
            )
            vod_total += cur.rowcount
        conn.commit()

        # 2. vod_tag
        try:
            cur.execute(
                "UPDATE public.vod_tag SET tag_value = %s "
                "WHERE tag_category IN ('director','actor_lead','actor_guest') AND tag_value = %s",
                (new_name, old_name),
            )
            tag_total += cur.rowcount
            conn.commit()
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            cur.execute(
                "DELETE FROM public.vod_tag "
                "WHERE tag_value = %s AND tag_category IN ('director','actor_lead','actor_guest')",
                (old_name,),
            )
            conn.commit()

        # 3. user_preference
        try:
            cur.execute(
                "UPDATE public.user_preference SET tag_value = %s "
                "WHERE tag_category IN ('director','actor_lead','actor_guest') AND tag_value = %s",
                (new_name, old_name),
            )
            pref_total += cur.rowcount
            conn.commit()
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            cur.execute(
                "DELETE FROM public.user_preference "
                "WHERE tag_value = %s AND tag_category IN ('director','actor_lead','actor_guest')",
                (old_name,),
            )
            pref_total += cur.rowcount
            conn.commit()

        if i % 100 == 0 or i == len(converted):
            print(f"  [{i}/{len(converted)}] 처리 완료", flush=True)

    cur.close()
    conn.close()

    print(f"\nvod 테이블: {vod_total:,} rows updated")
    print(f"vod_tag: {tag_total:,} rows updated")
    print(f"user_preference: {pref_total:,} rows updated")


if __name__ == "__main__":
    main()
