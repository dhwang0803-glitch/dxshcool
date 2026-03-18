"""
pilot_travel_test.py — YouTube 영상 다운로드 후 여행지 CLIP 인식 테스트

실행:
    cd Object_Detection
    python scripts/pilot_travel_test.py --url "https://www.youtube.com/watch?v=Otk49Yg7vCc"
    python scripts/pilot_travel_test.py --url "..." --fps 0.5 --threshold 0.24 --save-frames
"""
import sys
import argparse
import tempfile
import shutil
import yaml
import cv2
import numpy as np
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CONFIG_PATH = PROJECT_ROOT / "config" / "clip_queries_ko.yaml"

from frame_extractor import extract_frames
from clip_scorer import ClipScorer
from context_filter import ContextFilter


# ── 여행지 카테고리만 추출 ───────────────────────────────────────
TRAVEL_CATEGORY = "여행지"


def load_travel_queries(config_path: str):
    """yaml에서 여행지 + 도시_관광 + negative 쿼리 로드."""
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    queries = cfg["queries"]
    travel_qs    = queries.get(TRAVEL_CATEGORY, [])
    city_qs      = queries.get("도시_관광", [])
    negative_qs  = queries.get("negative", [])
    travel_groups = cfg.get("travel_groups", {})

    all_qs = travel_qs + city_qs + negative_qs
    qmap = {}
    for q in travel_qs:
        qmap[q] = TRAVEL_CATEGORY
    for q in city_qs:
        qmap[q] = "도시_관광"
    for q in negative_qs:
        qmap[q] = "negative"

    threshold = cfg.get("threshold", 0.26)
    model = cfg.get("model", "clip-ViT-B-32-multilingual-v1")
    return all_qs, qmap, threshold, model, travel_groups


def download_video(url: str, out_dir: Path) -> Path:
    """yt-dlp으로 YouTube 영상 다운로드 → 파일 경로 반환."""
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp 미설치. 실행: pip install yt-dlp")

    out_tmpl = str(out_dir / "%(id)s.%(ext)s")
    ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best",
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info.get("id", "video")

    # 다운로드된 파일 탐색
    mp4_files = list(out_dir.glob(f"{video_id}*.mp4"))
    if not mp4_files:
        mp4_files = list(out_dir.glob("*.mp4"))
    if not mp4_files:
        raise RuntimeError(f"다운로드 실패: {url}")
    return mp4_files[0]


def draw_score_bar(frame: np.ndarray, scores: dict[str, float],
                   qmap: dict[str, str], threshold: float) -> np.ndarray:
    """프레임 하단에 상위 여행지 쿼리 점수바 오버레이."""
    img = frame.copy()
    h, w = img.shape[:2]

    # 여행지 쿼리만, 점수 내림차순
    travel_scores = {q: s for q, s in scores.items()
                     if qmap.get(q) == TRAVEL_CATEGORY}
    top = sorted(travel_scores.items(), key=lambda x: -x[1])[:5]

    bar_h = 22
    y_start = h - bar_h * len(top) - 8

    for rank, (query, score) in enumerate(top):
        y = y_start + rank * bar_h
        bar_w = int(w * score)
        color = (0, 200, 80) if score >= threshold else (60, 60, 180)
        cv2.rectangle(img, (0, y), (bar_w, y + bar_h - 2), color, -1)
        label = f"{query[:22]}  {score:.3f}"
        cv2.putText(img, label, (4, y + bar_h - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)
    return img


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",       type=str,   required=True,  help="YouTube URL")
    parser.add_argument("--config",    type=str,   default=str(CONFIG_PATH))
    parser.add_argument("--fps",       type=float, default=0.5,    help="프레임 추출 fps")
    parser.add_argument("--threshold", type=float, default=None,   help="CLIP threshold (기본: yaml 값)")
    parser.add_argument("--save-frames", action="store_true",      help="탐지 프레임 저장")
    parser.add_argument("--no-and",      action="store_true",      help="AND 조건 비활성화 (테스트용)")
    args = parser.parse_args()

    queries, qmap, threshold, model_name, travel_groups = load_travel_queries(args.config)
    if args.threshold is not None:
        threshold = args.threshold

    print(f"\n[설정]")
    print(f"  URL       : {args.url}")
    print(f"  여행지 쿼리 : {len([q for q in queries if qmap[q] == TRAVEL_CATEGORY])}개")
    print(f"  negative  : {len([q for q in queries if qmap[q] == 'negative'])}개")
    print(f"  threshold : {threshold}")
    print(f"  fps       : {args.fps}")
    print(f"  모델      : {model_name}\n")

    # ── 영상 다운로드 ─────────────────────────────────────────────
    tmp_dir = Path(tempfile.mkdtemp(prefix="travel_test_"))
    try:
        print("영상 다운로드 중...")
        video_path = download_video(args.url, tmp_dir)
        print(f"다운로드 완료: {video_path.name}  ({video_path.stat().st_size / 1e6:.1f} MB)\n")

        # ── 프레임 추출 ───────────────────────────────────────────
        frames, timestamps = extract_frames(str(video_path), fps=args.fps)
        print(f"추출 프레임: {len(frames)}개 ({timestamps[0]:.1f}s ~ {timestamps[-1]:.1f}s)\n")

        # ── CLIP 스코어링 ─────────────────────────────────────────
        scorer = ClipScorer(model_name=model_name)
        print("CLIP 스코어링 중...")
        results = scorer.score_frames(frames, queries)

        # ── 프레임별 분석 ─────────────────────────────────────────
        hits = []           # (ts, query, score) threshold 이상
        suppressed = 0
        score_log = []      # 전체 score 분포용

        TRAVEL_CATS = {TRAVEL_CATEGORY, "도시_관광"}
        NEG_MARGIN  = 0.03   # negative가 travel보다 이 이상 높을 때만 억제

        ctx_filter = ContextFilter()
        for ts, scores in zip(timestamps, results):
            neg_scores    = [s for q, s in scores.items() if qmap.get(q) == "negative"]
            max_neg       = max(neg_scores) if neg_scores else 0.0

            # 여행지 + 도시_관광 모두 포함해서 max_travel 계산
            all_travel    = {q: s for q, s in scores.items() if qmap.get(q) in TRAVEL_CATS}
            max_travel    = max(all_travel.values()) if all_travel else 0.0

            score_log.append((ts, max_travel, max_neg))

            # negative가 travel보다 NEG_MARGIN 이상 클 때만 억제
            if max_neg > max_travel + NEG_MARGIN:
                suppressed += 1
                continue

            # 여행지 / 도시_관광 각각 체크
            frame_hit = False
            tg = None if args.no_and else travel_groups
            for cat in sorted(TRAVEL_CATS):  # 순서 고정
                cat_scores = {q: s for q, s in scores.items()
                              if qmap.get(q) == cat and s >= threshold}
                if not cat_scores:
                    continue
                ctx = ctx_filter.validate(
                    yolo_labels=set(),
                    clip_scores=scores,
                    ad_category=cat,
                    query_category_map=qmap,
                    threshold=threshold,
                    travel_groups=tg,
                )
                # 디버그: threshold 통과했으나 AND 실패한 프레임 표시
                if not ctx["context_valid"]:
                    floor = threshold - 0.04
                    if travel_groups and cat in travel_groups:
                        g_info = {g: max((scores.get(q, 0) for q in qs), default=0)
                                  for g, qs in travel_groups[cat].items()}
                        hit_gs = [g for g, s2 in g_info.items() if s2 >= floor]
                        print(f"  [AND 실패] ts={ts:.1f}s  cat={cat}  reason={ctx['context_reason']}")
                        for g, s2 in sorted(g_info.items(), key=lambda x: -x[1]):
                            mark = "✅" if s2 >= floor else "  "
                            print(f"    {mark} {g:<12} {s2:.3f}")
                    continue  # AND 실패해도 다음 카테고리 시도

                best_q = max(cat_scores, key=cat_scores.get)
                hits.append({"ts": ts, "query": best_q,
                             "score": cat_scores[best_q], "category": cat})
                frame_hit = True
                break

            if not frame_hit and any(
                s >= threshold for q, s in scores.items()
                if qmap.get(q) in TRAVEL_CATS
            ):
                suppressed += 1

        # ── 결과 출력 ─────────────────────────────────────────────
        print(f"\n{'='*60}")
        print(f"여행지 탐지 결과")
        print(f"{'='*60}")
        print(f"전체 프레임    : {len(frames)}개")
        print(f"negative 억제  : {suppressed}개")
        print(f"탐지 히트 수   : {len(hits)}건 (threshold={threshold})")
        print(f"AND floor      : {threshold - 0.04:.2f}  (그룹 히트 기준)")

        if hits:
            print(f"\n[탐지된 프레임 — 타임스탬프별]")
            ts_groups = defaultdict(list)
            for h in hits:
                ts_groups[h["ts"]].append((h["query"], h["score"]))

            for ts in sorted(ts_groups.keys()):
                top_q = sorted(ts_groups[ts], key=lambda x: -x[1])
                best_q, best_s = top_q[0]
                cat = hits[[h["ts"] for h in hits].index(ts)].get("category", "")
                others = ", ".join(f"{q[:15]}({s:.3f})" for q, s in top_q[1:3])
                print(f"  {ts:6.1f}s  [{cat}] ✅ {best_q[:28]:<28} {best_s:.3f}"
                      + (f"  | {others}" if others else ""))

            print(f"\n[쿼리별 탐지 횟수]")
            query_cnt = defaultdict(int)
            for h in hits:
                query_cnt[h["query"]] += 1
            for q, cnt in sorted(query_cnt.items(), key=lambda x: -x[1]):
                print(f"  {q:<40} {cnt:>4}회")
        else:
            print("\n탐지 없음 — score 분포 확인:")

        # ── score 분포 (threshold 관계없이 전체) ─────────────────
        print(f"\n[travel score 분포 — 전체 프레임]")
        print(f"  {'구간':<12} {'프레임 수':>8}")
        bins = [(0.30, 1.0), (0.28, 0.30), (0.26, 0.28), (0.24, 0.26),
                (0.22, 0.24), (0.20, 0.22), (0.0, 0.20)]
        for lo, hi in bins:
            cnt = sum(1 for _, s, _ in score_log if lo <= s < hi)
            bar = "█" * min(cnt, 40)
            print(f"  [{lo:.2f}~{hi:.2f})  {cnt:>5}  {bar}")

        # ── 프레임 저장 ───────────────────────────────────────────
        if args.save_frames and hits:
            out_dir = PROJECT_ROOT / "data" / "pilot_travel_frames"
            out_dir.mkdir(parents=True, exist_ok=True)
            print(f"\n프레임 저장: {out_dir}")

            saved = set()
            ts_to_frame = {round(ts, 3): f for ts, f in zip(timestamps, frames)}
            ts_to_scores = {round(ts, 3): sc for ts, sc in zip(timestamps, results)}

            for h in sorted(hits, key=lambda x: -x["score"]):
                key = round(h["ts"], 3)
                if key in saved:
                    continue
                saved.add(key)
                frame = ts_to_frame.get(key)
                if frame is None:
                    continue
                sc = ts_to_scores.get(key, {})
                annotated = draw_score_bar(frame, sc, qmap, threshold)
                safe_q = h["query"][:25].replace(" ", "_")
                fname = f"ts{h['ts']:06.1f}__{safe_q}__{h['score']:.3f}.jpg"
                ret, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 88])
                if ret:
                    buf.tofile(str(out_dir / fname))
            print(f"저장 완료: {len(saved)}개 프레임")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
