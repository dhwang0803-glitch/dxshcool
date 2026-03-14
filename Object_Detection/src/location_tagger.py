"""
location_tagger.py — 사용자 위치 기반 지역 태그 + 광고 힌트

현재: 랜덤 위치 시뮬레이션 (실서비스 시 실제 GPS로 대체)
역할: 비전으로 못 잡는 지역성을 위치 정보로 보완
"""
from __future__ import annotations
import random


# 한국 주요 시/도 위경도 경계 (근사값)
_REGION_MAP = [
    {"region": "서울특별시",   "lat": (37.4, 37.7), "lng": (126.8, 127.2)},
    {"region": "경기도",       "lat": (37.0, 37.8), "lng": (126.7, 127.8)},
    {"region": "인천광역시",   "lat": (37.3, 37.6), "lng": (126.4, 126.8)},
    {"region": "강원도",       "lat": (37.0, 38.7), "lng": (127.7, 129.4)},
    {"region": "충청남도",     "lat": (36.0, 37.1), "lng": (126.1, 127.4)},
    {"region": "충청북도",     "lat": (36.3, 37.2), "lng": (127.2, 128.5)},
    {"region": "전라북도",     "lat": (35.3, 36.3), "lng": (126.3, 127.8)},
    {"region": "전라남도",     "lat": (34.0, 35.5), "lng": (126.0, 127.8)},
    {"region": "경상북도",     "lat": (35.6, 37.0), "lng": (128.0, 129.6)},
    {"region": "경상남도",     "lat": (34.6, 35.9), "lng": (127.6, 129.5)},
    {"region": "부산광역시",   "lat": (35.0, 35.4), "lng": (128.8, 129.4)},
    {"region": "대구광역시",   "lat": (35.7, 36.0), "lng": (128.4, 128.8)},
    {"region": "제주특별자치도", "lat": (33.0, 33.7), "lng": (126.1, 126.9)},
]

# 지역별 광고 힌트 (특산물 / 여행 상품 카테고리)
_AD_HINTS: dict[str, list[str]] = {
    "서울특별시":     ["생활용품", "패션", "가전제품", "식품배달"],
    "경기도":         ["농산물", "가전제품", "생활용품"],
    "인천광역시":     ["수산물", "여행패키지", "면세품"],
    "강원도":         ["강원 감자", "황태", "오징어", "스키 여행", "평창 여행"],
    "충청남도":       ["홍성 한우", "태안 꽃게", "간월도 굴", "서산 마늘"],
    "충청북도":       ["청주 한우", "단양 마늘", "청양 고추"],
    "전라북도":       ["임실 치즈", "순창 고추장", "전주 한식"],
    "전라남도":       ["영광 굴비", "보성 녹차", "완도 전복", "여수 돌산 갓김치"],
    "경상북도":       ["영덕 대게", "울진 대게", "안동 한우", "문경 오미자"],
    "경상남도":       ["통영 굴", "남해 멸치", "하동 녹차", "거제 바다 여행"],
    "부산광역시":     ["기장 대게", "부산 어묵", "해운대 여행", "수산물"],
    "대구광역시":     ["사과", "섬유 패션", "가전제품"],
    "제주특별자치도": ["제주 감귤", "흑돼지", "한라봉", "제주 여행패키지"],
}


class LocationTagger:
    def random_location(self) -> tuple[float, float]:
        """한국 위경도 범위 내 랜덤 위치 생성 (위도, 경도)."""
        lat = round(random.uniform(33.0, 38.7), 4)
        lng = round(random.uniform(124.5, 132.0), 4)
        return lat, lng

    def get_region(self, lat: float, lng: float) -> str:
        """
        위경도 → 시/도 명 반환.
        매칭 없으면 "기타" 반환.
        """
        for r in _REGION_MAP:
            lat_min, lat_max = r["lat"]
            lng_min, lng_max = r["lng"]
            if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
                return r["region"]
        return "기타"

    def get_ad_hints(self, region: str) -> list[str]:
        """
        지역명 → 광고 카테고리 힌트 리스트.
        매칭 없으면 기본 힌트 반환.
        """
        return _AD_HINTS.get(region, ["생활용품", "식품", "여행패키지"])

    def tag(self, lat: float, lng: float) -> dict:
        """
        위경도 → {region, ad_hints} 반환.
        """
        region = self.get_region(lat, lng)
        return {
            "region":    region,
            "ad_hints":  self.get_ad_hints(region),
        }
