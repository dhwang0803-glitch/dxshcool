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
        for category, keywords in config.items():
            for keyword, meta in keywords.items():
                # 한국어 2글자 이하 키워드는 단어 경계 매칭 (오탐 방지)
                if len(keyword) <= 2:
                    pattern = re.compile(rf"(?<!\w){re.escape(keyword)}(?!\w)")
                else:
                    pattern = re.compile(re.escape(keyword))
                self._keyword_map[keyword] = {
                    "ad_category": category,
                    "ad_hints":    meta["ad_hints"],
                    "pattern":     pattern,
                }

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
        for keyword, meta in self._keyword_map.items():
            if meta["pattern"].search(transcript):
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
