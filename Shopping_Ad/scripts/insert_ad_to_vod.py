"""
insert_ad_to_vod.py — VOD 영상에 축제 팝업 GIF 삽입 (페이드인/아웃)

FFmpeg로 GIF→mp4 변환 → setpts 타임시프트 + fade → overlay

사용법:
    cd Shopping_Ad
    python scripts/insert_ad_to_vod.py
"""
import subprocess
import sys
import os
import shutil
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).parent.parent
REPO_ROOT = PROJECT_ROOT.parent

VOD_PATH = REPO_ROOT / "Object_Detection" / "data" / "batch_target" / "food_altoran_496.mp4"

TS_START = 891.19       # 트리거 시점 (초)
AD_DURATION = 10        # 광고 노출 시간 (초)
FADE_SEC = 1.5          # 페이드인/아웃 (초)
AD_W = 130              # 광고 표시 크기
AD_H = 76

OUTPUT_DIR = PROJECT_ROOT / "data" / "ad_gifs"
GIF_PATH = OUTPUT_DIR / "popup_창원_진해군항제.gif"
OUTPUT_PATH = OUTPUT_DIR / "sample_popup_진해군항제.mp4"


def main():
    if not VOD_PATH.exists():
        print(f"[ERROR] VOD 없음: {VOD_PATH}")
        sys.exit(1)
    if not GIF_PATH.exists():
        print(f"[ERROR] GIF 없음: {GIF_PATH}")
        sys.exit(1)

    ts_min = int(TS_START) // 60
    ts_sec = int(TS_START) % 60
    fade_out_start = TS_START + AD_DURATION - FADE_SEC

    print("=" * 55)
    print(f"  축제 팝업 -> VOD 삽입 (페이드인/아웃)")
    print(f"  VOD: {VOD_PATH.name}")
    print(f"  GIF: {GIF_PATH.name} -> {AD_W}x{AD_H}")
    print(f"  삽입: {ts_min}분 {ts_sec}초 ~ +{AD_DURATION}초")
    print("=" * 55)

    # 1) GIF → mp4 (한글 파일명 회피)
    tmp_gif = str(OUTPUT_DIR / "_tmp_ad.gif")
    tmp_ad = str(OUTPUT_DIR / "_tmp_ad.mp4")
    shutil.copy2(str(GIF_PATH), tmp_gif)

    print("  GIF -> mp4 변환 중...")
    r = subprocess.run([
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-t", str(AD_DURATION),
        "-i", tmp_gif,
        "-vf", f"scale={AD_W}:{AD_H}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", tmp_ad,
    ], capture_output=True)

    if not os.path.exists(tmp_ad) or os.path.getsize(tmp_ad) < 1000:
        stderr = r.stderr.decode("utf-8", errors="replace")[-500:]
        print(f"  [ERROR] GIF->mp4 변환 실패\n{stderr}")
        return

    # 2) VOD + 팝업 오버레이 (setpts 타임시프트 + fade)
    print("  풀 영상 인코딩 중... (시간 소요)")
    filter_complex = (
        f"[1:v]setpts=PTS+{TS_START}/TB,"
        f"fade=t=in:st={TS_START}:d={FADE_SEC},"
        f"fade=t=out:st={fade_out_start}:d={FADE_SEC}[ad];"
        f"[0:v][ad]overlay=W-w-15:H-h-15:eof_action=pass[out]"
    )

    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", str(VOD_PATH), "-i", tmp_ad,
        "-filter_complex", filter_complex,
        "-map", "[out]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "copy", str(OUTPUT_PATH),
    ], capture_output=True)

    # 정리
    for f in [tmp_gif, tmp_ad]:
        if os.path.exists(f):
            os.remove(f)

    if OUTPUT_PATH.exists() and OUTPUT_PATH.stat().st_size > 10000:
        size_mb = OUTPUT_PATH.stat().st_size / (1024 * 1024)
        print(f"  완료! {size_mb:.1f} MB")
        print(f"  >> {ts_min}분 {ts_sec}초에서 광고 확인")
    else:
        stderr = result.stderr.decode("utf-8", errors="replace")[-500:]
        print(f"  [ERROR] 생성 실패\n{stderr}")


if __name__ == "__main__":
    main()
