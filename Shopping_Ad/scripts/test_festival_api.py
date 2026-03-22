"""API 파라미터 테스트 — 어떤 형식이 작동하는지 확인"""
import requests
import json

API_URL = "https://korean.visitkorea.or.kr/kfes/list/selectWntyFstvlList.do"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://korean.visitkorea.or.kr/kfes/list/wntyFstvlList.do",
    "X-Requested-With": "XMLHttpRequest",
}

tests = [
    # (설명, content_type, data)
    ("form: searchDate=04월", "form", {"startIdx": "0", "searchType": "A", "searchDate": "04월"}),
    ("form: searchDate=4", "form", {"startIdx": "0", "searchType": "A", "searchDate": "4"}),
    ("form: searchDate=04", "form", {"startIdx": "0", "searchType": "A", "searchDate": "04"}),
    ("form: searchDate=2026.04", "form", {"startIdx": "0", "searchType": "A", "searchDate": "2026.04"}),
    ("form: searchDate=개최예정", "form", {"startIdx": "0", "searchType": "A", "searchDate": "개최예정"}),
    ("json: searchDate=04월", "json", {"startIdx": 0, "searchType": "A", "searchDate": "04월"}),
    ("json: searchDate=개최예정", "json", {"startIdx": 0, "searchType": "A", "searchDate": "개최예정"}),
    ("form: 빈값 전체", "form", {"startIdx": "0", "searchType": "A"}),
    ("form: page2", "form", {"startIdx": "12", "searchType": "A"}),
    ("form: page3", "form", {"startIdx": "24", "searchType": "A"}),
]

for desc, ctype, data in tests:
    try:
        if ctype == "form":
            resp = requests.post(API_URL, headers=HEADERS, data=data, timeout=10)
        else:
            resp = requests.post(API_URL, headers=HEADERS, json=data, timeout=10)

        result = resp.json()
        items = result.get("resultList", [])
        if items:
            first = items[0].get("cntntsNm", "?")
            last = items[-1].get("cntntsNm", "?")
            dates = [i.get("fstvlBgngDe", "") for i in items]
            print(f"✅ {desc}: {len(items)}건 | {first} ~ {last} | 날짜: {dates[0]}~{dates[-1]}")
        else:
            print(f"❌ {desc}: 0건")
    except Exception as e:
        print(f"💥 {desc}: {e}")
