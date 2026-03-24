"""
test_festival_match.py — 축제 매칭 E2E 검증

Object_Detection 테스트 결과(region)로 축제 매칭이 되는지 검증.

실행:
    cd Shopping_Ad
    python scripts/test_festival_match.py
"""
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from festival_matcher import FestivalMatcher

DATA_DIR = PROJECT_ROOT / "data"


def main():
    yaml_path = DATA_DIR / "region_festivals.yaml"
    if not yaml_path.exists():
        print("❌ region_festivals.yaml 없음. crawl_festivals.py 먼저 실행하세요.")
        return

    matcher = FestivalMatcher(str(yaml_path))
    print(f"{'=' * 60}")
    print(f"  축제 매칭 E2E 검증")
    print(f"  축제 데이터: {matcher.festival_count}건 / {len(matcher.regions)}개 지역")
    print(f"{'=' * 60}")

    # Object_Detection 테스트 영상에서 나온 region들
    test_cases = [
        # (영상, region, 기대 결과)
        ("test12 순천 여행", "순천", True),
        ("test1 전주 먹방", "전주", False),   # 전주는 4~5월 축제 없을 수도
        ("test2 부산/거제", "부산", True),
        ("test3 경주 여행", "경주", True),
        ("서울촌놈 1화", "부산", True),
        ("서울촌놈 3화", "광주", False),
        ("서울촌놈 5화", "청주", True),
        ("서울촌놈 7화", "대전", True),
        ("서울촌놈 9화", "전주", False),
        ("동원아 6화", "영월", True),
        ("동원아 11화", "정선", False),
        ("동원아 12화", "삼척", True),
        ("동원아 16화", "제주", True),
        ("로컬식탁 보령", "보령", True),
        ("로컬식탁 여수", "여수", True),
        ("로컬식탁 춘천", "춘천", True),
        # 없는 지역
        ("없는 지역", "평양", False),
    ]

    match_count = 0
    no_match = []

    for desc, region, _ in test_cases:
        results = matcher.match(region)
        if results:
            match_count += 1
            print(f"\n  ✅ {desc} → region='{region}'")
            for r in results[:3]:
                print(f"     📍 {r['popup_title']}")
                print(f"     {r['popup_body']}")
            if len(results) > 3:
                print(f"     ... +{len(results)-3}건")
        else:
            no_match.append((desc, region))
            print(f"\n  ⬜ {desc} → region='{region}' → 매칭 없음")

    print(f"\n{'=' * 60}")
    print(f"  결과: {match_count}/{len(test_cases)} 매칭")
    print(f"  매칭 안 됨: {[f'{d}({r})' for d, r in no_match]}")
    print(f"{'=' * 60}")

    # 매칭 가능 지역 전체 출력
    print(f"\n  매칭 가능 지역 ({len(matcher.regions)}개):")
    for r in sorted(matcher.regions):
        festivals = matcher.match(r)
        names = ", ".join(f["festival_name"][:20] for f in festivals[:2])
        print(f"    {r}: {names}")


if __name__ == "__main__":
    main()
