"""시연사이트 미번역 인물 이름 → 한국어 일괄 변환 (v2).

Notion 작업문서 '시연사이트:감독,주연 (ENG)' 2건에서 식별된 잔여 미번역 이름.
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
    # ══════════════════════════════════════════════════════════
    # 1. 영문 로마자 한국인 이름
    # ══════════════════════════════════════════════════════════
    "Lee Hyun-seok": "이현석",
    "Han Joon-seo": "한준서",
    "Jung Sang-hee": "정상희",
    "Lee Jae-hoon": "이재훈",
    "Lee Jae-jin": "이재진",
    "Kim Bo-sol": "김보솔",
    "Seo Won-seok": "서원석",
    "Jung Ho-seung": "정호승",
    "Kim Ha-rim": "김하림",
    "Jung Chae-hee": "정채희",
    "Lee Sun-myung": "이선명",
    "Maeng Joo-gong": "맹주공",
    "Cheon Yu-rim": "천유림",
    "Seong Si-seon": "성시선",
    "Seo Guk-han": "서국한",
    "Kim Mare": "김마레",
    "Lee Elly": "이엘리",
    "Lee Jooin": "이주인",
    "Kim Kwan-tae": "김관태",
    "Kim Tae-Kyun": "김태균",
    "Bae Jung-hun": "배정훈",
    "Park Seong-bae": "박성배",
    "Kwak Jeong-eun": "곽정은",
    "Son Min-su": "손민수",
    "Lee Cheon-eun": "이천은",
    "Park Sung-jun": "박성준",
    "Kim Sang-hyub": "김상협",
    "Park Sung Hwan": "박성환",
    "Kim Yoo-gon": "김유곤",
    "Heo An-na": "허안나",
    "Myung Jae Wook": "명재욱",
    "Kwon Sung-wook": "권성욱",
    "Park Dae-min": "박대민",
    "Choi Jeong-min": "최정민",
    "Mok Gyu-ri": "목규리",
    "Kim Hakr-yong": "김학용",
    "Choi Eul": "최을",
    "Jeong Hoe-dong": "정회동",
    "Lee Seo-jun": "이서준",
    "Lee Chang-woo": "이창우",
    "Kim Jin": "김진",
    "Yang Seul-gi": "양슬기",
    "Seong Chi Kyung": "성치경",
    "You Sun-dong": "유선동",
    "Kang Sung-pil": "강성필",
    "Jeon Soo-jin": "전수진",
    "Yoon Yeo-chang": "윤여창",
    "You Jay": "유제이",
    "An Ayoung": "안아영",
    "Joo Dong-min": "주동민",

    # ══════════════════════════════════════════════════════════
    # 2. 러시아어
    # ══════════════════════════════════════════════════════════
    "Тимур Бекмамбетов": "티무르 베크맘베토프",

    # ══════════════════════════════════════════════════════════
    # 3. 일본어 한자
    # ══════════════════════════════════════════════════════════
    "橋爪駿輝": "하시즈메 슌키",
    "榊一郎": "사카키 이치로",
    "笹沼晃": "사사누마 아키라",
    "山田能龍": "야마다 요시타츠",
    "中村海人": "나카무라 카이토",
    "里見瑤子": "사토미 요코",
    "辻凪子": "츠지 나기코",

    # ══════════════════════════════════════════════════════════
    # 4. 중국어 한자
    # ══════════════════════════════════════════════════════════
    "劉芮麟": "류예린",

    # ══════════════════════════════════════════════════════════
    # 5. 영문 외국인 이름 (음차)
    # ══════════════════════════════════════════════════════════

    # ── 홈ver ──
    "Piper Curda": "파이퍼 커다",
    "Kathy Najimy": "캐시 나지미",
    "Kylie Rogers": "카일리 로저스",
    "Chris Sullivan": "크리스 설리번",
    "Elizabeth Perkins": "엘리자베스 퍼킨스",
    "Ric Roman Waugh": "릭 로만 워",
    "Michael Shaeffer": "마이클 셰퍼",
    "Anna Crilly": "안나 크릴리",
    "Eugenia Caruso": "유지니아 카루소",
    "Celine Buckens": "셀린 버켄스",
    "Craig Brewer": "크레이그 브루어",
    "Maya da Costa": "마야 다 코스타",
    "Myra Molloy": "마이라 몰로이",
    "Levon Hawke": "레본 호크",
    "Remy Marthaller": "레미 마탈러",
    "Maya Ford": "마야 포드",
    "Alozie LaRose": "알로지 라로즈",
    "Hunter Dillon": "헌터 딜런",
    "Dimitrius Schuster-Koloamatangi": "디미트리우스 슈스터-콜로아마탕이",
    "Ravi Narayan": "라비 나라얀",
    "Michael Homick": "마이클 호믹",
    "Stefan Grube": "슈테판 그루베",
    "Emma Tammi": "엠마 태미",
    "Freddy Carter": "프레디 카터",
    "Kai Shindo": "카이 신도",
    "Mayumi Asona": "마유미 아소나",
    "Tatsuya Kobashi": "타츠야 코바시",
    "Gil Bellows": "길 벨로즈",
    "James Whitmore": "제임스 휘트모어",
    "Mark Rolston": "마크 롤스턴",
    "Marc Thompson": "마크 톰슨",
    "Barrett Leddy": "바렛 레디",
    "Samantha Cooper": "사만다 쿠퍼",
    "James Brown Jr.": "제임스 브라운 주니어",
    "Diane Baker": "다이앤 베이커",
    "Kasi Lemmons": "카시 레먼스",
    "Robert Connolly": "로버트 코놀리",
    "Genevieve O'Reilly": "제네비브 오라일리",
    "Keir O'Donnell": "키어 오도넬",
    "John Polson": "존 폴슨",
    "Matt Nable": "맷 네이블",
    "Eddie Baroo": "에디 바루",
    "Martin Dingle Wall": "마틴 딩글 월",
    "Julia Blake": "줄리아 블레이크",
    "Clarke Peters": "클라크 피터스",
    "Edward Holcroft": "에드워드 홀크로프트",
    "Kevin Rahm": "케빈 람",
    "Michael Hyatt": "마이클 하이앳",
    "Price Carson": "프라이스 카슨",
    "Kent Shocknek": "켄트 쇼크넥",
    "Robert Wuhl": "로버트 울",
    "Pat Hingle": "팻 힝글",
    "Michael Gough": "마이클 고프",
    "Mike Johnson": "마이크 존슨",
    "Paul Whitehouse": "폴 화이트하우스",
    "Melissa O'Neil": "멜리사 오닐",
    "Eric Winter": "에릭 윈터",
    "Alyssa Diaz": "앨리사 디아즈",
    "Veronica Cartwright": "베로니카 카트라이트",
    "Yaphet Kotto": "야펫 코토",
    "Bolaji Badejo": "볼라지 바데조",
    "Elizabeth Rodriguez": "엘리자베스 로드리게즈",
    "Boyd Holbrook": "보이드 홀브룩",
    "Stephen Dunlevy": "스티븐 던레비",
    "Tim Pigott-Smith": "팀 피곳스미스",
    "Roger Allam": "로저 앨럼",
    "Kyle Schmid": "카일 슈미드",
    "María Conchita Alonso": "마리아 콘치타 알론소",
    "KeiLyn Durrel Jones": "케이린 더렐 존스",
    "Clara Wong": "클라라 웡",
    "Michelle Veintimilla": "미셸 베인티밀라",
    "Marc Lawrence": "마크 로렌스",
    "Caroline Aaron": "캐럴라인 아론",
    "Steven Kaplan": "스티븐 캐플런",
    "Neil LaBute": "닐 라뷰트",

    # ── 스마트 추천ver ──
    "David Dencik": "데이비드 덴식",
    "Meat Loaf": "미트 로프",
    "Zach Grenier": "잭 그레니어",
    "Malgorzata Gebel": "말고자타 게벨",
    "Ethan Phillips": "에단 필립스",
    "Brian Stepanek": "브라이언 스테파넥",
    "Nate Lang": "네이트 랭",
    "Samantha Mahurin": "사만다 마후린",
    "Frank Finlay": "프랭크 핀레이",
    "Maureen Lipman": "모린 립먼",
    "Emilia Fox": "에밀리아 폭스",
    "Ed Stoppard": "에드 스토파드",
    "Julia Rayner": "줄리아 레이너",
    "Jessica Kate Meyer": "제시카 케이트 마이어",

    # 블랙팬서 (다큐멘터리)
    "Huey P. Newton": "휴이 P. 뉴턴",
    "Eldridge Cleaver": "엘드리지 클리버",
    "Bobby Seale": "바비 실",
    "Kwame Ture": "콰메 투레",
    "Ron Dellums": "론 델럼스",
    "James Forman": "제임스 포먼",
    "H. Rap Brown": "H. 랩 브라운",
    "Kathleen Cleaver": "캐슬린 클리버",

    # 리유니언
    "Jake Mahaffy": "제이크 마하피",
    "Emma Draper": "엠마 드레이퍼",
    "Cohen Holloway": "코언 홀로웨이",
    "Ava Keane": "에이바 킨",
    "Gina Laverty": "지나 라버티",
    "John Bach": "존 바흐",
    "Dra McKay": "드라 맥케이",
    "Patricia Wilton": "패트리샤 윌턴",

    # 제네시스·파바로티·리슨
    "Juliano Ribeiro Salgado": "줄리아누 히베이루 살가두",
    "Hugo Barbier": "위고 바르비에",
    "Tim Haines": "팀 헤인스",
    "Luciano Pavarotti": "루치아노 파바로티",
    "Harvey Goldsmith": "하비 골드스미스",
    "Nicoletta Mantovani": "니콜레타 만토바니",
    "Andrea Griminelli": "안드레아 그리미넬리",
    "Ana Rocha de Sousa": "아나 호샤 드 소우자",
    "Ruben Garcia": "루벤 가르시아",
    "Maisie Sly": "메이지 슬라이",
    "James Felner": "제임스 펠너",
    "Sophia Myles": "소피아 마일스",
    "Brian Bovell": "브라이언 보벨",
    "Jay Lycurgo": "제이 라이커고",
    "Aldo Maland": "알도 말란드",

    # 막후지왕 (중국 드라마)
    "Li Jun": "리준",
    "Wu Lipeng": "우리펑",

    # 기타
    "Erika Alexander": "에리카 알렉산더",
    "Kiyoto Naruse": "키요토 나루세",
    "Yohei Sekiguchi": "요헤이 세키구치",
    "Naoto Kawashima": "나오토 가와시마",

    # 태국 (셔터)
    "Unnop Chanpaibool": "운놉 찬파이분",
    "Titikarn Tongprasearth": "티티칸 통프라서트",
    "Sivagorn Muttamara": "시바곤 뭇타마라",
    "Chachchaya Chalemphol": "차차야 찰렘폰",
    "Kachornsak Naruepatr": "가쫀삭 나루에팟",
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
