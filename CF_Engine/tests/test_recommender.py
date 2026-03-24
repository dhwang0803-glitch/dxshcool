"""tests/test_recommender.py — recommender 단위 테스트"""

import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.recommender import build_records


def test_build_records_output_format():
    user_dec = {0: "user_A", 1: "user_B"}
    item_dec = {0: "vod_X", 1: "vod_Y", 2: "vod_Z"}

    user_ids = [0, 1]
    item_indices = np.array([[0, 1], [2, 0]])
    scores = np.array([[0.9, 0.7], [0.8, 0.6]])

    records = build_records(user_ids, item_indices, scores,
                            user_dec, item_dec, recommendation_type="CF")

    assert len(records) == 4
    assert records[0]["user_id_fk"] == "user_A"
    assert records[0]["vod_id_fk"] == "vod_X"
    assert records[0]["rank"] == 1
    assert records[1]["rank"] == 2


def test_build_records_reverse_mapping():
    user_dec = {0: "u1"}
    item_dec = {0: "v1", 1: "v2"}

    user_ids = [0]
    item_indices = np.array([[1, 0]])
    scores = np.array([[0.95, 0.85]])

    records = build_records(user_ids, item_indices, scores,
                            user_dec, item_dec)

    assert records[0]["vod_id_fk"] == "v2"
    assert records[1]["vod_id_fk"] == "v1"


def test_recommendation_type_in_records():
    user_dec = {0: "u1"}
    item_dec = {0: "v1"}
    user_ids = [0]
    item_indices = np.array([[0]])
    scores = np.array([[0.9]])

    records = build_records(user_ids, item_indices, scores,
                            user_dec, item_dec, recommendation_type="ALS")
    assert records[0]["recommendation_type"] == "ALS"
