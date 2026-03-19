"""
keyword_mapper.py — STT transcript 키워드 매핑

transcript 텍스트에서 stt_keywords.yaml 키워드를 탐지하여
ad_category + ad_hints 레코드를 생성한다.
"""
from __future__ import annotations
import re
import yaml
import random
from pathlib import Path


class KeywordMapper:
    """
    match(transcript, vod_id, start_ts, end_ts) → list[dict]
    """

    def __init__(self, config_path: str):
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # {키워드: {"ad_category": str, "ad_hints": list, "pattern": re.Pattern}}
        self._keyword_map: dict[str, dict] = {}
        all_keywords = []
        for category, keywords in config.items():
            for keyword, meta in keywords.items():
                all_keywords.append(keyword)
                # 한국어 조사("을/를/이/가/은/는/의/에/로/와/과/도") 허용,
                # 그 외 한글이 이어지면 매칭 거부 ("오리지널"에서 "오리" 차단)
                esc = re.escape(keyword)
                pattern = re.compile(
                    rf"{esc}(?=[을를이가은는의에로와과도서까지만]|[^가-힣]|$)"
                )
                self._keyword_map[keyword] = {
                    "ad_category": category,
                    "ad_hints":    meta["ad_hints"],
                    "pattern":     pattern,
                }

        # 포함관계 키워드 제거: "콩나물" 매칭 시 "나물" 중복 방지
        # 긴 키워드 우선 — 짧은 키워드가 긴 키워드에 포함되면 _contained_by에 등록
        sorted_kws = sorted(all_keywords, key=len, reverse=True)
        self._contained_by: dict[str, list[str]] = {}
        for i, short in enumerate(sorted_kws):
            for long in sorted_kws[:i]:
                if short != long and short in long:
                    self._contained_by.setdefault(short, []).append(long)
                    break

    def match(
        self,
        transcript: str,
        vod_id: str,
        start_ts: float,
        end_ts: float,
    ) -> list[dict]:
        """
        transcript에서 키워드 탐지 → 레코드 리스트 반환.
        한 구간에 복수 키워드 → 복수 레코드.

        Returns:
            list of {vod_id, start_ts, end_ts, transcript, keyword,
                     ad_category, ad_hints, context_valid, context_reason}
        """
        records = []
        matched_keywords = set()
        for keyword, meta in self._keyword_map.items():
            if meta["pattern"].search(transcript):
                matched_keywords.add(keyword)

        # 포함관계 제거: "콩나물" 매칭됐으면 "나물" 스킵
        for short, longs in self._contained_by.items():
            if short in matched_keywords:
                if any(l in matched_keywords for l in longs):
                    matched_keywords.discard(short)

        for keyword in matched_keywords:
            meta = self._keyword_map[keyword]
            records.append({
                "vod_id":         vod_id,
                "start_ts":       start_ts,
                "end_ts":         end_ts,
                "transcript":     transcript,
                "keyword":        keyword,
                "ad_category":    meta["ad_category"],
                "ad_hints":       random.choice(meta["ad_hints"]),
                "context_valid":  True,
                "context_reason": "keyword_match",
            })
        return records
