"""v8 파일럿 실행 래퍼 — result_B_v8.json 저장 (JustWatch + DATA_GO 연동)"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "RAG" / "src"))

# run_approach_b를 직접 실행하되 OUTPUT_JSON만 변경
import run_approach_b as m
m.OUTPUT_JSON = ROOT / "RAG" / "reports" / "result_B_v8.json"
m.main()
