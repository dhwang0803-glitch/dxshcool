"""외국어 인물 이름 → 한국어 일괄 변환.

vod (director, cast_lead, cast_guest) + vod_tag + user_preference 3개 테이블 업데이트.
"""
import sys
import os

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

import psycopg2
from dotenv import load_dotenv

load_dotenv()


NAME_MAP = {
    # ══ Batch 1 (완료) ══════════════════════════════════════
    # 영문 로마자 한국인
    "Lee Jang-woo": "이장우",
    "Heo Hang": "허항",
    "Lee Ju-seung": "이주승",
    "Code Kunst": "코드 쿤스트",
    "Choi Sam-ho": "최삼호",
    "Lee Seung-jun": "이승준",
    "Lee Won-tae": "이원태",
    "Choi Chul-min": "최철민",
    "Jung Dae-yoon": "정대윤",
    "Shin Kyung-soo": "신경수",
    "An Tae-jin": "안태진",
    "Park Ki-hyun": "박기현",
    "Park Man Young": "박만영",
    "Key": "키",
    "BE'O": "비오",
    "Brian Le": "브라이언 르",
    # 영문 로마자 외국인
    "Yang-Chung Fan": "범양중",
    "Chin-Bao Yu": "유진보",
    "Aria Wang": "왕아리아",
    "Takuya Kato": "가토 타쿠야",
    "Miho Kaneno": "카네노 미호",
    # 한자 (중국/대만)
    "莫允雯": "막윤문",
    "范少勳": "범소훈",
    "温貞菱": "온정릉",
    "納豆": "납두",
    "陳以文": "진이문",
    "王琄": "왕현",
    "杨恩又": "양은우",
    "陳鍵鋒": "진건봉",
    "徐冬冬": "서동동",
    "单明凯": "단명개",
    "童辉": "동휘",
    # 한자 (일본)
    "谷垣健治": "타니가키 켄지",
    "谷村美月": "타니무라 미츠키",
    "仲里依紗": "나카리이사",
    "垣内彩未": "카키우치 아야미",
    "石田卓也": "이시다 타쿠야",
    "板倉光隆": "이타쿠라 미츠타카",
    "桂歌若": "카츠라 우타와카",
    "関戸優希": "세키도 유키",
    "栗原颯人": "쿠리하라 하야토",
    # ══ Batch 2 (1000+ users 잔여) ══════════════════════════
    # 영문 로마자 한국인
    "Park Sung-hoon": "박성훈",
    "Nam Hyeon-hee": "남현희",
    "Lee Hyung Sun": "이형선",
    "Kim Si-heon": "김시헌",
    "Park Sang-woo": "박상우",
    "Go Young-tak": "고영탁",
    "Park Cheol-ho": "박철호",
    "Jung Su-hwan": "정수환",
    "Choi Yun-la": "최윤라",
    "Bae Noo-ri": "배누리",
    "Min Yeon-hong": "민연홍",
    "Kang Sun A": "강선아",
    "Im Jin-soon": "임진순",
    "Jin Hyung-wook": "진형욱",
    "Kim Moon-kyo": "김문교",
    "Kim Sol-bi": "김솔비",
    "Choi Sun-ja": "최선자",
    "Seo Ju-hyeong": "서주형",
    "Lee Soon-sung": "이순성",
    "Park Ki-ho": "박기호",
    "Park Da-eun": "박다은",
    "Lee Chang-min": "이창민",
    "Yu Je-won": "유제원",
    "Jang Do-yeon": "장도연",
    "Yoo Se-yoon": "유세윤",
    "Kim Gu-ra": "김구라",
    "Kim Guk-jin": "김국진",
    "Park Na-eun": "박나은",
    "Park Joo-ho": "박주호",
    "Han Jae-yeong": "한재영",
    "Park Sang-hyeon": "박상현",
    "Jang Hyung-won": "장형원",
    "Choi Jong-il": "최종일",
    "Koo Ja-hyoung": "구자형",
    "Kim Yong-im": "김용임",
    "Jaeho Ryu": "류재호",
    "Moon Hyun-sung": "문현성",
    # 영문 외국인 → 한국어 음차
    "Alexander Siddig": "알렉산더 시디그",
    "Taylor Kitsch": "테일러 키취",
    "Louis Cancelmi": "루이스 캔셀미",
    "Brian Kirk": "브라이언 커크",
    "Zain Al Rafeea": "자인 알 라피아",
    "Kawsar Al Haddad": "카우사르 알 하다드",
    "Cedra Izzam": "세드라 이잠",
    "Boluwatife Treasure Bankole": "볼루와티페 트레저 뱅콜레",
    "Fadi Kamel Yousef": "파디 카멜 유세프",
    "Elias Khoury": "엘리아스 쿠리",
    "Yordanos Shifera": "요르다노스 시페라",
    "Alaa Chouchnieh": "알라 추슈니에",
    "Leyla Bouzid": "레일라 부지드",
    "Mathilde La Musse": "마틸드 라 뮈스",
    "Samir Elhakim": "사미르 엘하킴",
    "Bellamine Abdelmalek": "벨라민 압델말렉",
    "Zbeida Belhajamor": "즈베이다 벨하자모르",
    "Sami Outalbali": "사미 우탈발리",
    "Mahia Zrouki": "마히아 즈루키",
    "Vahina Giocante": "바이나 지오칸테",
    "Yves Verhoeven": "이브 베르후벤",
    "Marie Matheron": "마리 마테롱",
    "Adrienne Pauly": "아드리엔 폴리",
    "Clovis Cornillac": "클로비스 코르니약",
    "Jacques Gamblin": "자크 감블랭",
    "Marie Bunel": "마리 뷔넬",
    "Shina Peng": "시나 펑",
    "Yukito Hidaka": "히다카 유키토",
    "Arazi": "아라지",
    # 중국 (적인걸)
    "Sun Xiaomeng": "쑨 샤오멍",
    "Nan Chuer": "난 추얼",
    "Zhang Bonan": "장 보난",
    "Liu Guanqi": "류 관치",
    # 일본
    "矢作優": "야하기 유",
}


def main():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()

    print(f"총 {len(NAME_MAP)}개 이름 매핑", flush=True)

    vod_total = 0
    tag_total = 0
    pref_total = 0

    for i, (old_name, new_name) in enumerate(NAME_MAP.items(), 1):
        # ── 1. vod (REPLACE — 항상 안전) ──
        for col in ("director", "cast_lead", "cast_guest"):
            cur.execute(
                f"UPDATE public.vod SET {col} = REPLACE({col}, %s, %s) WHERE {col} LIKE %s",
                (old_name, new_name, f"%{old_name}%"),
            )
            vod_total += cur.rowcount
        conn.commit()

        # ── 2. vod_tag: UPDATE 먼저, 충돌 시 DELETE 후 재시도 ──
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

        # ── 3. user_preference: UPDATE 먼저, 충돌 시 DELETE 후 재시도 ──
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

        print(f"  [{i}/{len(NAME_MAP)}] {old_name} -> {new_name}", flush=True)

    cur.close()
    conn.close()

    print(f"\nvod 테이블: {vod_total:,} rows updated")
    print(f"vod_tag: {tag_total:,} rows updated")
    print(f"user_preference: {pref_total:,} rows updated")


if __name__ == "__main__":
    main()
