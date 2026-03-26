"""
generate_festival_gif.py — 축제 팝업 HTML → Playwright 캡처 → GIF 변환

1. templates/popup_*.html을 헤드리스 브라우저로 렌더링
2. 프레임별 스크린샷 캡처
3. Pillow로 GIF 합성

실행:
    cd Shopping_Ad
    python scripts/generate_festival_gif.py
"""
import sys
import io
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PIL import Image
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).parent.parent
TEMPLATE_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "data" / "ad_gifs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── GIF 설정 ──
VIEWPORT_W = 520
VIEWPORT_H = 300
TOTAL_SEC = 5.0         # 총 캡처 시간
FRAME_INTERVAL = 100    # ms 간격 → 10fps
GIF_DURATION = 100      # GIF 프레임 재생 속도 (ms)
INIT_WAIT = 3000        # 초기 렌더링 대기 (폰트+JS+CSS 애니메이션 시작)

POPUP_FESTIVALS = [
    ("popup_cherry_blossom.html", "popup_창원_진해군항제.gif"),
    ("popup_danjong.html",        "popup_영월_단종문화제.gif"),
    ("popup_jejuma.html",         "popup_제주_제주마입목문화축제.gif"),
    ("popup_haeundae.html",       "popup_부산_해운대모래축제.gif"),
    ("popup_mulbit.html",         "popup_대전_대덕물빛축제.gif"),
    ("popup_mime.html",           "popup_춘천_춘천마임축제.gif"),
]


def capture_frames(html_path):
    """HTML → Playwright 프레임 캡처 → PIL Image 리스트"""
    num_frames = int(TOTAL_SEC * 1000 / FRAME_INTERVAL)
    file_url = html_path.resolve().as_uri()
    frames = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            device_scale_factor=2,
        )

        page.goto(file_url, wait_until="networkidle")
        page.wait_for_timeout(INIT_WAIT)

        print(f"  {num_frames}프레임 캡처 중...")
        for i in range(num_frames):
            shot = page.screenshot(type="png", omit_background=True)
            img = Image.open(io.BytesIO(shot)).convert("RGBA")
            img = img.resize((VIEWPORT_W, VIEWPORT_H), Image.LANCZOS)
            frames.append(img)

            if i < num_frames - 1:
                page.wait_for_timeout(FRAME_INTERVAL)

        browser.close()

    print(f"  {len(frames)}프레임 캡처 완료")
    return frames


def save_gif(frames, output_path):
    """RGBA 프레임 → GIF 저장 (흰색 배경)"""
    rgb = []
    for f in frames:
        bg = Image.new("RGB", f.size, (255, 255, 255))
        bg.paste(f, mask=f.split()[3])
        rgb.append(bg)

    rgb[0].save(
        str(output_path),
        save_all=True,
        append_images=rgb[1:],
        duration=GIF_DURATION,
        loop=0,
        optimize=True,
    )


def main():
    print(f"\n{'='*50}")
    print(f"[팝업 GIF 생성] {VIEWPORT_W}x{VIEWPORT_H}, {TOTAL_SEC}초, {FRAME_INTERVAL}ms 간격")
    print(f"초기 대기: {INIT_WAIT}ms\n")

    for html_name, gif_name in POPUP_FESTIVALS:
        html_path = TEMPLATE_DIR / html_name
        if not html_path.exists():
            print(f"[SKIP] 템플릿 없음: {html_name}")
            continue

        output_path = OUTPUT_DIR / gif_name
        print(f"--- {html_name} -> {gif_name} ---")

        frames = capture_frames(html_path)
        save_gif(frames, output_path)

        size_kb = output_path.stat().st_size / 1024
        print(f"  GIF 생성: {size_kb:.1f} KB, {len(frames)}장\n")


if __name__ == "__main__":
    main()
