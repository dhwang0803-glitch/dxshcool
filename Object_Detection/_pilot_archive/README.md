# _pilot_archive

Phase 1~5 파일럿/실험용 스크립트 보관. git 추적 제외.

| 파일 | 원래 위치 | 용도 |
|------|-----------|------|
| `pilot_yolo_test.py` | scripts/ | Phase 1 YOLO 단독 테스트 |
| `pilot_yolo_ab_test.py` | scripts/ | best.pt vs COCO A/B 비교 |
| `pilot_yolo_v2_test.py` | scripts/ | detector_v2 단독 테스트 |
| `pilot_clip_test.py` | scripts/ | Phase 2 CLIP 단독 테스트 |
| `pilot_travel_test.py` | scripts/ | 관광지 CLIP 테스트 |
| `analyze_pilot.py` | scripts/ | Phase 5 학습 결과 분석 |
| `prepare_local_dataset.py` | scripts/ | Phase 5 데이터 전처리 |
| `split_val.py` | scripts/ | Phase 5 train/val 분할 |
| `detector.py` | src/ | YOLO v1 래퍼 (v2로 대체) |
| `food_class_names.yaml` | config/ | 71 카테고리명 (파인튜닝 전용) |
| `food_menu_names.yaml` | config/ | 761 메뉴명 (파인튜닝 전용) |
