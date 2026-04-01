"""
festival_matcher.py — Object_Detection region → 축제 매칭

Object_Detection에서 추출한 region(지역명)을 Visit Korea 축제 데이터와 매칭하여
지자체 광고 팝업 데이터를 생성한다.

사용:
    from festival_matcher import FestivalMatcher
    matcher = FestivalMatcher("data/region_festivals.yaml")
    result = matcher.match("순천")
    # → [{"name": "순천만 ...", "period": "2026.04.03~...", "popup": "..."}]
"""
from __future__ import annotations
import yaml
from pathlib import Path
from datetime import datetime


class FestivalMatcher:
    """region → 축제 매칭 엔진"""

    def __init__(self, yaml_path: str):
        with open(yaml_path, encoding="utf-8") as f:
            self._region_map: dict[str, list[dict]] = yaml.safe_load(f) or {}

    @property
    def regions(self) -> list[str]:
        """매칭 가능한 지역 목록"""
        return list(self._region_map.keys())

    @property
    def festival_count(self) -> int:
        return sum(len(v) for v in self._region_map.values())

    def match(self, region: str) -> list[dict]:
        """
        지역명 → 해당 지역 축제 목록 반환.
        매칭 없으면 빈 리스트.
        """
        if not region:
            return []

        # 정확 매칭
        festivals = self._region_map.get(region, [])
        if festivals:
            return [self._enrich(f, region) for f in festivals]

        # 부분 매칭 (예: "순천만" → "순천")
        for key in self._region_map:
            if key in region or region in key:
                return [self._enrich(f, key) for f in self._region_map[key]]

        return []

    def match_multiple(self, regions: list[str]) -> list[dict]:
        """여러 지역 매칭 → 중복 제거"""
        seen = set()
        results = []
        for r in regions:
            for f in self.match(r):
                key = f["festival_name"]
                if key not in seen:
                    seen.add(key)
                    results.append(f)
        return results

    def _enrich(self, festival: dict, region: str) -> dict:
        """축제 데이터에 팝업 메시지 추가"""
        name = festival.get("name", "")
        period = festival.get("period", "")
        return {
            "festival_name": name,
            "region": region,
            "period": period,
            "ad_action_type": "local_gov_popup",
            "popup_title": f"📍 {region} 축제 안내",
            "popup_body": f"{name}\n📅 {period}",
        }
