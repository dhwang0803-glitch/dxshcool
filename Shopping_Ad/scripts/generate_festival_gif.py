"""
generate_festival_gif.py — HTML 템플릿 → Playwright 캡처 → GIF 변환

1. templates/ 폴더의 축제 HTML을 헤드리스 브라우저로 렌더링
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
VIEWPORT_W = 480
VIEWPORT_H = 360
TOTAL_SEC = 5.0         # 총 캡처 시간
FRAME_INTERVAL = 100    # ms 간격 → 10fps
GIF_DURATION = 100      # GIF 프레임 재생 속도 (ms)
INIT_WAIT = 3000        # 초기 렌더링 대기 (폰트+JS+CSS 애니메이션 시작)


def capture_html_frames(html_path):
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
        # 폰트 + CSS 애니메이션 시작 대기
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


def save_gif(frames, output_path, bg_color=(5, 5, 5)):
    """RGBA 프레임 → GIF 저장"""
    rgb = []
    for f in frames:
        bg = Image.new("RGB", f.size, bg_color)
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
    html_path = TEMPLATE_DIR / "overlay_cherry_blossom.html"
    if not html_path.exists():
        print(f"템플릿 없음: {html_path}")
        return

    output_path = OUTPUT_DIR / "festival_changwon.gif"

    print(f"템플릿: {html_path.name}")
    print(f"뷰포트: {VIEWPORT_W}x{VIEWPORT_H}, {TOTAL_SEC}초, {FRAME_INTERVAL}ms 간격")
    print(f"초기 대기: {INIT_WAIT}ms (폰트/애니메이션 로딩)")

    frames = capture_html_frames(html_path)
    save_gif(frames, output_path)

    size_kb = output_path.stat().st_size / 1024
    print(f"\nGIF 생성: {output_path}")
    print(f"크기: {size_kb:.1f} KB, 프레임: {len(frames)}장")


if __name__ == "__main__":
    main()
