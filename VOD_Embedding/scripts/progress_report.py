"""
크롤링 + 임베딩 진행 현황 보고서 출력 + 파일 저장
실행: python scripts/progress_report.py
저장: VOD_Embedding/docs/reports/crawl_progress/progress_YYYYMMDD_HHMMSS.md
"""
import json, os, sys
from pathlib import Path
from datetime import datetime
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT  = Path(__file__).parent.parent
DATA_DIR      = PROJECT_ROOT / "data"
TRAILERS_DIR  = DATA_DIR / "trailers"
REPORT_DIR    = PROJECT_ROOT / "docs" / "reports" / "crawl_progress"

def load_json(path):
    if Path(path).exists():
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return {}

def fmt(n): return f"{n:,}"

def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    crawl = load_json(DATA_DIR / "crawl_status.json")
    embed = load_json(DATA_DIR / "embed_status.json")

    # ── 크롤링 현황 ─────────────────────────
    total_target   = crawl.get("total", 0)
    processed      = crawl.get("processed", 0)
    success        = crawl.get("success", 0)
    failed         = crawl.get("failed", 0)
    last_updated   = crawl.get("last_updated", "N/A")

    pct = f"{processed/total_target*100:.1f}%" if total_target else "0%"
    success_rate = f"{success/processed*100:.1f}%" if processed else "0%"

    # ct_cl별 성공/실패
    vods = crawl.get("vods", {})
    ct_success = Counter()
    ct_failed  = Counter()
    for v in vods.values():
        ct = v.get("ct_cl", "unknown")
        if v.get("status") == "success":
            ct_success[ct] += 1
        else:
            ct_failed[ct] += 1

    # trailers 폴더 디스크 사용량
    trailer_files = list(TRAILERS_DIR.glob("*")) if TRAILERS_DIR.exists() else []
    disk_mb = sum(f.stat().st_size for f in trailer_files if f.is_file()) / (1024*1024)

    # ── parquet 현황 ─────────────────────────
    parquet_files = list(DATA_DIR.glob("embeddings_*.parquet")) + list(DATA_DIR.glob("embeddings_output.parquet"))
    parquet_rows  = 0
    parquet_size  = 0
    for pf in parquet_files:
        try:
            import pandas as pd
            df = pd.read_parquet(pf)
            parquet_rows += len(df)
            parquet_size += pf.stat().st_size / (1024*1024)
        except Exception:
            pass

    # ── 임베딩 현황 ─────────────────────────
    embed_processed = embed.get("processed", 0)
    embed_success   = embed.get("success", 0)
    embed_failed    = embed.get("failed", 0)
    embed_batches   = len(embed.get("batches_completed", []))

    # ── 출력 ─────────────────────────────────
    print(f"\n{'='*55}")
    print(f"  VOD_Embedding 중간점검 — {now}")
    print(f"{'='*55}")

    print(f"\n[STEP 1] 트레일러 크롤링")
    print(f"  대상      : {fmt(total_target)}건 (tasks_C.json)")
    print(f"  처리완료  : {fmt(processed)}건 ({pct})")
    print(f"  성공      : {fmt(success)}건  ({success_rate})")
    print(f"  실패      : {fmt(failed)}건")
    print(f"  디스크    : {disk_mb:.1f} MB ({len(trailer_files)}개 파일)")
    print(f"  마지막갱신: {last_updated}")

    if ct_success:
        print(f"\n  ct_cl별 성공:")
        for ct, n in sorted(ct_success.items(), key=lambda x: -x[1]):
            f_n = ct_failed.get(ct, 0)
            total_ct = n + f_n
            print(f"    {ct:<20} 성공 {fmt(n):>6} / 시도 {fmt(total_ct):>6}")

    print(f"\n[STEP 2] CLIP 임베딩")
    if embed_processed == 0:
        print(f"  상태: 대기 중 (크롤링 완료 후 실행 예정)")
    else:
        print(f"  처리완료  : {fmt(embed_processed)}건")
        print(f"  성공      : {fmt(embed_success)}건")
        print(f"  실패      : {fmt(embed_failed)}건")
        print(f"  저장배치  : {embed_batches}개")

    print(f"\n[STEP 3] Parquet 출력")
    if parquet_rows == 0:
        print(f"  상태: 미생성")
    else:
        for pf in parquet_files:
            print(f"  {pf.name}: {parquet_rows:,}건, {parquet_size:.1f}MB")

    # 남은 시간 예측 (크롤링 기준)
    if processed > 0 and total_target > processed:
        remaining = total_target - processed
        # crawl.log에서 시작 시간 추정
        log_path = DATA_DIR / "crawl.log"
        if log_path.exists():
            lines = log_path.read_text(encoding='utf-8', errors='ignore').splitlines()
            start_lines = [l for l in lines if "작업 파일 로드" in l and "dry" not in l.lower()]
            if start_lines:
                try:
                    start_str = start_lines[-1][:19]
                    start_dt  = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
                    elapsed   = (datetime.now() - start_dt).total_seconds()
                    rate      = processed / elapsed   # 건/초
                    eta_sec   = remaining / rate
                    eta_h     = int(eta_sec // 3600)
                    eta_m     = int((eta_sec % 3600) // 60)
                    print(f"\n  예상 남은 시간: {eta_h}시간 {eta_m}분 (현재 {rate*60:.1f}건/분)")
                except Exception:
                    pass

    print(f"\n{'='*55}\n")

    # ── 파일 저장 ─────────────────────────────
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = REPORT_DIR / f"progress_{ts}.md"

    lines = [
        f"# VOD_Embedding 중간점검 — {now}",
        f"",
        f"## STEP 1. 트레일러 크롤링",
        f"",
        f"| 항목 | 값 |",
        f"|------|---|",
        f"| 대상 | {fmt(total_target)}건 (tasks_C.json) |",
        f"| 처리완료 | {fmt(processed)}건 ({pct}) |",
        f"| 성공 | {fmt(success)}건 ({success_rate}) |",
        f"| 실패 | {fmt(failed)}건 |",
        f"| 디스크 | {disk_mb:.1f} MB ({len(trailer_files)}개 파일) |",
        f"| 마지막 갱신 | {last_updated} |",
        f"",
    ]

    if ct_success:
        lines += [f"### ct_cl별 성공", f"", f"| 유형 | 성공 | 시도 |", f"|------|-----:|-----:|"]
        for ct, n in sorted(ct_success.items(), key=lambda x: -x[1]):
            f_n = ct_failed.get(ct, 0)
            lines.append(f"| {ct} | {fmt(n)} | {fmt(n+f_n)} |")
        lines.append("")

    lines += [
        f"## STEP 2. CLIP 임베딩",
        f"",
        f"| 항목 | 값 |",
        f"|------|---|",
    ]
    if embed_processed == 0:
        lines.append(f"| 상태 | 대기 중 (크롤링 완료 후 실행 예정) |")
    else:
        lines += [
            f"| 처리완료 | {fmt(embed_processed)}건 |",
            f"| 성공 | {fmt(embed_success)}건 |",
            f"| 실패 | {fmt(embed_failed)}건 |",
            f"| 저장배치 | {embed_batches}개 |",
        ]
    lines.append("")

    lines += [f"## STEP 3. Parquet 출력", f""]
    if parquet_rows == 0:
        lines.append("상태: 미생성")
    else:
        for pf in parquet_files:
            lines.append(f"- `{pf.name}`: {parquet_rows:,}건, {parquet_size:.1f} MB")
    lines.append("")

    # ETA
    if processed > 0 and total_target > processed:
        log_path = DATA_DIR / "crawl.log"
        if log_path.exists():
            log_lines = log_path.read_text(encoding='utf-8', errors='ignore').splitlines()
            start_lines = [l for l in log_lines if "작업 파일 로드" in l and "dry" not in l.lower()]
            if start_lines:
                try:
                    start_dt = datetime.strptime(start_lines[-1][:19], "%Y-%m-%d %H:%M:%S")
                    elapsed  = (datetime.now() - start_dt).total_seconds()
                    rate     = processed / elapsed
                    eta_sec  = (total_target - processed) / rate
                    eta_h    = int(eta_sec // 3600)
                    eta_m    = int((eta_sec % 3600) // 60)
                    lines += [
                        f"## 예상 남은 시간",
                        f"",
                        f"- 크롤링 속도: {rate*60:.1f}건/분",
                        f"- 남은 시간: **{eta_h}시간 {eta_m}분**",
                        f"",
                    ]
                except Exception:
                    pass

    filename.write_text("\n".join(lines), encoding='utf-8')
    print(f"[저장] {filename}")


if __name__ == "__main__":
    main()
