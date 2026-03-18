"""
Cold VOD 비중이 추천에 미치는 영향 분석
- filter_quality OFF vs ON 시 행렬 크기 비교
- 유저별 cold VOD 시청 비율 분포
- cold 비중 높은 유저(>50%) 규모 파악

실행: python scripts/cold_impact_analysis.py
"""

import sys
import logging
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from src.data_loader import get_conn, load_matrix

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def main():
    conn = get_conn()

    log.info("filter_quality OFF 행렬 로드 중...")
    mat_off, user_enc_off, item_enc_off, user_dec_off, item_dec_off = load_matrix(
        conn, alpha=40, filter_quality=False
    )

    log.info("filter_quality ON 행렬 로드 중...")
    mat_on, user_enc_on, item_enc_on, user_dec_on, item_dec_on = load_matrix(
        conn, alpha=40, filter_quality=True
    )

    # 유저별 cold VOD 시청 비율 계산
    log.info("유저별 cold 비율 계산 중...")
    cold_ratios = []
    for uid_str, uid_off in user_enc_off.items():
        total = mat_off.getrow(uid_off).nnz
        if total == 0:
            continue
        warm = user_enc_on.get(uid_str)
        warm_count = mat_on.getrow(warm).nnz if warm is not None else 0
        cold_ratio = (total - warm_count) / total
        cold_ratios.append(cold_ratio)

    cold_ratios = np.array(cold_ratios)

    # 구간별 분포
    buckets = [0, 0.1, 0.25, 0.5, 0.75, 1.01]
    labels = ["0~10%", "10~25%", "25~50%", "50~75%", "75~100%"]
    counts = []
    for i in range(len(buckets) - 1):
        cnt = int(((cold_ratios >= buckets[i]) & (cold_ratios < buckets[i + 1])).sum())
        counts.append(cnt)

    total_users = len(cold_ratios)
    heavy_cold = int((cold_ratios > 0.5).sum())  # cold 50% 초과
    zero_cold = int((cold_ratios == 0).sum())     # cold 없음

    conn.close()

    # 출력
    print("\n" + "=" * 60)
    print("  Cold VOD 비중이 추천에 미치는 영향 분석")
    print("=" * 60)

    print(f"\n[행렬 크기 비교]")
    print(f"  filter OFF — 유저: {mat_off.shape[0]:,}명 / 아이템: {mat_off.shape[1]:,}개")
    print(f"  filter ON  — 유저: {mat_on.shape[0]:,}명 / 아이템: {mat_on.shape[1]:,}개")
    print(f"  아이템 감소: {mat_off.shape[1] - mat_on.shape[1]:,}개 "
          f"({(mat_off.shape[1] - mat_on.shape[1]) / mat_off.shape[1] * 100:.1f}%)")

    print(f"\n[유저별 cold VOD 시청 비율 분포] (전체 {total_users:,}명)")
    print(f"  {'구간':>10} | {'유저 수':>8} | {'비율':>6} | 바")
    print(f"  {'-'*50}")
    for label, cnt in zip(labels, counts):
        bar = "█" * int(cnt / total_users * 30)
        print(f"  {label:>10} | {cnt:>8,}명 | {cnt/total_users*100:>5.1f}% | {bar}")

    print(f"\n[핵심 지표]")
    print(f"  cold VOD 전혀 없는 유저:    {zero_cold:,}명 ({zero_cold/total_users*100:.1f}%)")
    print(f"  cold 비중 50% 초과 유저:    {heavy_cold:,}명 ({heavy_cold/total_users*100:.1f}%)")
    print(f"  cold 비율 중앙값:           {np.median(cold_ratios)*100:.1f}%")
    print(f"  cold 비율 평균:             {cold_ratios.mean()*100:.1f}%")
    print("=" * 60)

    # 리포트 저장
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = Path("docs") / f"cold_impact_report_{timestamp}.md"
    report_path.parent.mkdir(exist_ok=True)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Cold VOD 비중 영향 분석 리포트\n\n")
        f.write(f"- **일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("## 행렬 크기 비교\n\n")
        f.write("| 구분 | 유저 수 | 아이템 수 |\n|------|---------|----------|\n")
        f.write(f"| filter OFF | {mat_off.shape[0]:,}명 | {mat_off.shape[1]:,}개 |\n")
        f.write(f"| filter ON | {mat_on.shape[0]:,}명 | {mat_on.shape[1]:,}개 |\n")
        f.write(f"| 감소 | - | {mat_off.shape[1]-mat_on.shape[1]:,}개 "
                f"({(mat_off.shape[1]-mat_on.shape[1])/mat_off.shape[1]*100:.1f}%) |\n\n")

        f.write("## 유저별 cold VOD 시청 비율 분포\n\n")
        f.write(f"전체 분석 유저: {total_users:,}명\n\n")
        f.write("| cold 비율 구간 | 유저 수 | 비율 |\n|----------------|---------|------|\n")
        for label, cnt in zip(labels, counts):
            f.write(f"| {label} | {cnt:,}명 | {cnt/total_users*100:.1f}% |\n")

        f.write("\n## 핵심 지표\n\n")
        f.write(f"| 항목 | 값 |\n|------|----|\n")
        f.write(f"| cold VOD 전혀 없는 유저 | {zero_cold:,}명 ({zero_cold/total_users*100:.1f}%) |\n")
        f.write(f"| cold 비중 50% 초과 유저 | {heavy_cold:,}명 ({heavy_cold/total_users*100:.1f}%) |\n")
        f.write(f"| cold 비율 중앙값 | {np.median(cold_ratios)*100:.1f}% |\n")
        f.write(f"| cold 비율 평균 | {cold_ratios.mean()*100:.1f}% |\n")

    log.info("리포트 저장: %s", report_path)
    print(f"\n✓ 리포트: {report_path}")


if __name__ == "__main__":
    main()
