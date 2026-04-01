"""
generate_all_festival_gifs.py — 크롤링한 전체 축제 대상 팝업 GIF 일괄 생성

1. festivals.json 읽기 (63건)
2. 축제별 팝업 HTML 자동 생성 (이미지 URL + 테마색 자동 배정)
3. Playwright 캡처 → GIF 합성
4. data/ad_gifs/ 에 저장

실행:
    cd Shopping_Ad
    python scripts/generate_all_festival_gifs.py
"""
import sys
import io
import json
import hashlib
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PIL import Image
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = DATA_DIR / "ad_gifs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TMP_HTML = PROJECT_ROOT / "templates" / "_tmp_popup.html"

# ── GIF 설정 ──
VW, VH = 520, 300
TOTAL_SEC = 5.0
FRAME_INTERVAL = 100
GIF_DURATION = 100
INIT_WAIT = 3500

# ── 카테고리별 테마 (키워드 매칭으로 자동 분류) ──
CATEGORY_THEMES = {
    "벚꽃":   {"primary": "#db2777", "badge_bg": "rgba(236,72,153,0.9)", "icon_bg": "#fce7f3", "glow": "rgba(244,114,182,0.15)", "subtitle": "봄꽃이 물드는 거리"},
    "꽃":     {"primary": "#e11d48", "badge_bg": "rgba(225,29,72,0.9)",  "icon_bg": "#ffe4e6", "glow": "rgba(244,63,94,0.15)",   "subtitle": "꽃향기 가득한 봄날"},
    "유채":   {"primary": "#ca8a04", "badge_bg": "rgba(202,138,4,0.9)",  "icon_bg": "#fef9c3", "glow": "rgba(250,204,21,0.15)",  "subtitle": "노란 물결이 출렁이는"},
    "바다":   {"primary": "#0891b2", "badge_bg": "rgba(8,145,178,0.9)",  "icon_bg": "#cffafe", "glow": "rgba(103,232,249,0.15)", "subtitle": "바다와 함께하는 축제"},
    "모래":   {"primary": "#0891b2", "badge_bg": "rgba(8,145,178,0.9)",  "icon_bg": "#cffafe", "glow": "rgba(103,232,249,0.15)", "subtitle": "바다와 모래의 예술"},
    "역사":   {"primary": "#b45309", "badge_bg": "rgba(180,120,40,0.9)", "icon_bg": "#fef3c7", "glow": "rgba(245,180,60,0.15)",  "subtitle": "역사가 숨 쉬는 고장"},
    "전통":   {"primary": "#92400e", "badge_bg": "rgba(146,64,14,0.9)",  "icon_bg": "#fef3c7", "glow": "rgba(217,119,6,0.15)",   "subtitle": "전통과 문화의 향연"},
    "도자":   {"primary": "#92400e", "badge_bg": "rgba(146,64,14,0.9)",  "icon_bg": "#fef3c7", "glow": "rgba(217,119,6,0.15)",   "subtitle": "흙과 불의 예술"},
    "빛":     {"primary": "#7c3aed", "badge_bg": "rgba(124,58,237,0.9)", "icon_bg": "#ede9fe", "glow": "rgba(167,139,250,0.15)", "subtitle": "빛으로 물드는 밤"},
    "야행":   {"primary": "#6d28d9", "badge_bg": "rgba(109,40,217,0.9)", "icon_bg": "#ede9fe", "glow": "rgba(139,92,246,0.15)",  "subtitle": "밤이 아름다운 여행"},
    "음식":   {"primary": "#ea580c", "badge_bg": "rgba(234,88,12,0.9)",  "icon_bg": "#ffedd5", "glow": "rgba(251,146,60,0.15)",  "subtitle": "맛있는 축제 한마당"},
    "차":     {"primary": "#059669", "badge_bg": "rgba(5,150,105,0.9)",  "icon_bg": "#d1fae5", "glow": "rgba(52,211,153,0.15)",  "subtitle": "향긋한 차 한 잔의 여유"},
    "자연":   {"primary": "#059669", "badge_bg": "rgba(5,150,105,0.9)",  "icon_bg": "#d1fae5", "glow": "rgba(52,211,153,0.15)",  "subtitle": "자연 속으로 떠나는 여행"},
    "산":     {"primary": "#16a34a", "badge_bg": "rgba(22,163,74,0.9)",  "icon_bg": "#dcfce7", "glow": "rgba(74,222,128,0.15)",  "subtitle": "산이 품은 축제"},
    "나비":   {"primary": "#059669", "badge_bg": "rgba(5,150,105,0.9)",  "icon_bg": "#d1fae5", "glow": "rgba(52,211,153,0.15)",  "subtitle": "자연이 선물한 날갯짓"},
    "공연":   {"primary": "#be123c", "badge_bg": "rgba(190,18,60,0.9)",  "icon_bg": "#ffe4e6", "glow": "rgba(244,63,94,0.15)",   "subtitle": "무대 위의 감동"},
    "마임":   {"primary": "#be123c", "badge_bg": "rgba(190,18,60,0.9)",  "icon_bg": "#ffe4e6", "glow": "rgba(244,63,94,0.15)",   "subtitle": "몸짓으로 전하는 이야기"},
    "우주":   {"primary": "#0284c7", "badge_bg": "rgba(2,132,199,0.9)",  "icon_bg": "#e0f2fe", "glow": "rgba(56,189,248,0.15)",  "subtitle": "우주를 향한 꿈"},
    "연등":   {"primary": "#d97706", "badge_bg": "rgba(217,119,6,0.9)",  "icon_bg": "#fef3c7", "glow": "rgba(251,191,36,0.15)",  "subtitle": "빛의 기원을 따라"},
    "기본":   {"primary": "#0284c7", "badge_bg": "rgba(2,132,199,0.9)",  "icon_bg": "#e0f2fe", "glow": "rgba(56,189,248,0.15)",  "subtitle": "함께 즐기는 축제"},
}

# 키워드 매칭 우선순위 (앞에 있을수록 우선)
KEYWORD_ORDER = [
    "벚꽃", "유채", "모래", "바다", "마임", "연등", "우주", "야행",
    "도자", "차", "나비", "빛", "음식", "역사", "전통", "산", "자연", "공연", "꽃",
]


# 수동 오버라이드 (자동 분류 오류 보정)
MANUAL_OVERRIDE = {
    "진해군항제":           "벚꽃",
    "단종문화제":           "역사",
    "이천백사 산수유꽃축제":    "꽃",
    "담양 대나무축제":       "자연",
    "연천구석기축제":        "역사",
    "홍성남당항 새조개축제":    "음식",
    "양평산수유한우축제":      "음식",
    "유달산 봄축제":         "꽃",
    "덕수궁 밤의 석조전":     "야행",
    "양주 회암사지 왕실축제":   "역사",
    "아산 성웅 이순신축제":    "역사",
    "밀양아리랑대축제":       "전통",
    "서울국제정원박람회":      "꽃",
    "서울스프링페스티벌":      "꽃",
    "의령 홍의장군 축제":     "역사",
    "윤봉길 평화축제":       "역사",
    "고창청보리밭 축제":      "자연",
    "제주마 입목 문화축제":    "자연",
    "김제 꽃빛드리 축제":     "꽃",
    "세종낙화축제":          "빛",
}


def classify_festival(fest):
    """축제명 + description 기반 카테고리 자동 분류 (수동 오버라이드 우선)"""
    import re
    name = fest["festival_name"]

    if name in MANUAL_OVERRIDE:
        return MANUAL_OVERRIDE[name]

    desc = re.sub(r'<[^>]+>', '', fest.get("description", ""))
    text = name + " " + desc[:200]

    for kw in KEYWORD_ORDER:
        if kw in text:
            return kw
    return "기본"


def get_theme(fest):
    """축제 → 카테고리 → 테마 색상 + 부제 반환"""
    cat = classify_festival(fest)
    theme = CATEGORY_THEMES[cat].copy()
    theme["category"] = cat
    return theme


# CDN 이미지가 안 뜨는 축제 → 로컬 사진으로 대체
LOCAL_IMAGES = {
    "함평나비대축제": (PROJECT_ROOT / "templates" / "images" / "hampyeong.jpg").resolve().as_uri(),
}


def make_popup_html(fest, theme):
    """축제 데이터 + 테마 → 팝업 HTML 생성"""
    name = fest["festival_name"]
    addr = fest.get("address", fest.get("region_full", ""))
    addr_short = " ".join(addr.split()[:3]) if addr else fest.get("region_full", "")
    date_str = f"{fest['start_date']} — {fest['end_date']}"
    img_url = LOCAL_IMAGES.get(name, fest.get("image_url", ""))
    subtitle = theme.get("subtitle", "함께 즐기는 축제")
    p = theme["primary"]
    badge = theme["badge_bg"]
    icon_bg = theme["icon_bg"]
    glow = theme["glow"]

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700;900&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Noto Sans KR',sans-serif; background:transparent; width:520px; height:300px; }}
.card {{
    width:520px; height:300px; border-radius:20px; overflow:hidden;
    position:relative; box-shadow:0 20px 40px rgba(0,0,0,0.4);
    border:1px solid rgba(255,255,255,0.3);
    animation: slideUp 1s cubic-bezier(0.23,1,0.32,1) forwards;
}}
@keyframes slideUp {{ from {{ transform:translateY(40px); opacity:0; }} to {{ transform:translateY(0); opacity:1; }} }}
@keyframes imageSway {{ 0%,100% {{ transform:scale(1.15) translateX(-8px); }} 50% {{ transform:scale(1.15) translateX(8px); }} }}
.bg-photo {{
    position:absolute; inset:0;
    background: url('{img_url}') center center / cover no-repeat, linear-gradient(135deg, {glow} 0%, rgba(245,245,250,0.95) 100%);
    animation: imageSway 15s ease-in-out infinite;
}}
.white-gradient {{
    position:absolute; inset:0; z-index:5;
    background: linear-gradient(to right, rgba(255,255,255,0.97) 0%, rgba(255,255,255,0.88) 45%, rgba(255,255,255,0.3) 72%, transparent 88%);
}}
@keyframes shimmer {{ 0%,100% {{ opacity:0; transform:scale(0.5); }} 50% {{ opacity:1; transform:scale(1); }} }}
.shimmer {{
    position:absolute; background:white; border-radius:50%;
    animation:shimmer ease-in-out infinite;
    box-shadow:0 0 6px 2px {glow};
    pointer-events:none; z-index:15;
}}
.content {{
    position:absolute; inset:0; padding:28px 32px;
    display:flex; flex-direction:column; justify-content:center; gap:16px; z-index:20;
}}
@keyframes spinSlow {{ from {{ transform:rotate(0deg); }} to {{ transform:rotate(360deg); }} }}
.badge {{
    display:inline-flex; align-items:center; gap:5px;
    background:{badge}; color:#fff;
    font-size:13px; font-weight:700; padding:4px 14px; border-radius:20px; width:fit-content;
}}
.badge svg {{ animation:spinSlow 3s linear infinite; }}
.title-sub {{ font-size:18px; font-weight:700; color:#444; line-height:1.3; margin-top:4px; text-shadow:0 0 8px rgba(255,255,255,0.8); }}
.title-main {{ font-size:34px; font-weight:900; color:{p}; margin-top:2px; line-height:1.1; text-shadow:0 1px 6px rgba(255,255,255,0.9); }}
.info-section {{ display:flex; flex-direction:column; gap:6px; margin-top:4px; }}
.info-row {{ display:flex; align-items:center; gap:10px; color:#374151; font-size:16px; font-weight:700; }}
.info-icon {{ background:{icon_bg}; padding:4px; border-radius:5px; display:flex; align-items:center; justify-content:center; }}
.glow-bg {{ position:absolute; inset:-6px; background:{glow}; border-radius:26px; filter:blur(16px); z-index:-1; }}
</style>
</head>
<body>
<div class="glow-bg"></div>
<div class="card">
    <div class="bg-photo"></div>
    <div class="white-gradient"></div>
    <div id="shimmerStream"></div>
    <div class="content">
        <div>
            <div class="badge">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 16.8l-6.2 4.5 2.4-7.4L2 9.4h7.6z"/></svg>
                지역축제
            </div>
            <div class="title-sub">{subtitle}</div>
            <div class="title-main">{name}</div>
        </div>
        <div class="info-section">
            <div class="info-row">
                <div class="info-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="{p}" stroke-width="2.5"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg></div>
                {addr_short}
            </div>
            <div class="info-row">
                <div class="info-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="{p}" stroke-width="2.5"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg></div>
                {date_str}
            </div>
        </div>
    </div>
</div>
<script>
function createShimmer() {{
    var c=document.getElementById('shimmerStream'); c.innerHTML='';
    for(var i=0;i<10;i++) {{
        var s=document.createElement('div'); s.className='shimmer';
        var size=2+Math.random()*3;
        s.style.width=size+'px'; s.style.height=size+'px';
        s.style.left=280+Math.random()*220+'px';
        s.style.top=30+Math.random()*160+'px';
        s.style.animationDelay=Math.random()*4+'s';
        s.style.animationDuration=1.5+Math.random()*2+'s';
        c.appendChild(s);
    }}
}}
createShimmer(); setInterval(createShimmer,6000);
</script>
</body>
</html>"""


def capture_and_save_gif(html_path, output_path, browser):
    """HTML → Playwright 캡처 → GIF 저장"""
    num_frames = int(TOTAL_SEC * 1000 / FRAME_INTERVAL)
    file_url = html_path.resolve().as_uri()

    page = browser.new_page(
        viewport={"width": VW, "height": VH},
        device_scale_factor=2,
    )
    page.goto(file_url, wait_until="networkidle")
    page.wait_for_timeout(INIT_WAIT)

    frames = []
    for i in range(num_frames):
        shot = page.screenshot(type="png", omit_background=True)
        img = Image.open(io.BytesIO(shot)).convert("RGBA")
        img = img.resize((VW, VH), Image.LANCZOS)
        frames.append(img)
        if i < num_frames - 1:
            page.wait_for_timeout(FRAME_INTERVAL)

    page.close()

    # GIF 저장 (흰색 배경)
    rgb = []
    for f in frames:
        bg = Image.new("RGB", f.size, (255, 255, 255))
        bg.paste(f, mask=f.split()[3])
        rgb.append(bg)

    rgb[0].save(
        str(output_path), save_all=True,
        append_images=rgb[1:], duration=GIF_DURATION,
        loop=0, optimize=True,
    )
    return len(frames)


def main():
    festivals_path = DATA_DIR / "festivals.json"
    if not festivals_path.exists():
        print(f"[ERROR] festivals.json 없음: {festivals_path}")
        sys.exit(1)

    with open(festivals_path, encoding="utf-8") as f:
        festivals = json.load(f)

    print(f"\n{'='*55}")
    print(f"  전체 축제 팝업 GIF 일괄 생성")
    print(f"  대상: {len(festivals)}건")
    print(f"  뷰포트: {VW}x{VH}, {TOTAL_SEC}초, {FRAME_INTERVAL}ms")
    print(f"{'='*55}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for i, fest in enumerate(festivals):
            name = fest["festival_name"]
            region = fest["region"]
            gif_name = f"popup_{region}_{name}.gif"
            output_path = OUTPUT_DIR / gif_name

            if output_path.exists():
                print(f"  [{i+1}/{len(festivals)}] SKIP (이미 존재): {gif_name}")
                continue

            theme = get_theme(fest)
            html_content = make_popup_html(fest, theme)

            TMP_HTML.write_text(html_content, encoding="utf-8")

            cat = theme.get("category", "?")
            sub = theme.get("subtitle", "")
            print(f"  [{i+1}/{len(festivals)}] [{cat}] {name} ({region}) — {sub}")

            try:
                n = capture_and_save_gif(TMP_HTML, output_path, browser)
                size_kb = output_path.stat().st_size / 1024
                print(f"    -> {gif_name} ({size_kb:.0f}KB, {n}프레임)")
            except Exception as e:
                print(f"    -> [ERROR] {e}")

        browser.close()

    # 임시 HTML 정리
    if TMP_HTML.exists():
        TMP_HTML.unlink()

    # 결과 요약
    gifs = list(OUTPUT_DIR.glob("popup_*.gif"))
    print(f"\n{'='*55}")
    print(f"  완료! {len(gifs)}개 GIF 생성됨")
    print(f"  경로: {OUTPUT_DIR}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
