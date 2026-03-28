"""
detector_v2.py — YOLO 2단계 추론 (COCO 사전필터 + 파인튜닝 메뉴 탐지)

1단계: COCO YOLO로 음식 관련 물체(bowl, cup, fork 등) 존재 확인
2단계: 음식 컨텍스트가 있는 프레임에서만 파인튜닝 모델 결과 채택

이렇게 하면:
  - 사람 얼굴 → "해천탕" 같은 오탐 차단 (COCO에서 food context 없음)
  - 김치찌개 냄비 → COCO "bowl" 탐지 → 파인튜닝 결과 채택
"""
from ultralytics import YOLO

# COCO 클래스 중 음식 컨텍스트로 인정하는 것들
FOOD_CONTEXT_CLASSES = {
    # 식기/조리도구
    "bowl", "cup", "fork", "knife", "spoon",
    "wine glass", "bottle",
    # 음식 직접
    "banana", "apple", "sandwich", "orange", "broccoli",
    "carrot", "hot dog", "pizza", "donut", "cake",
    # 식탁/주방
    "dining table", "oven", "microwave",
}

# COCO 클래스 중 음식과 무관한 것 (이것만 있으면 food context 아님)
NON_FOOD_ONLY = {"person", "car", "truck", "bus", "bicycle", "motorcycle",
                 "cat", "dog", "horse", "bird", "tv", "laptop", "cell phone"}


def _iou(box_a, box_b):
    """두 bbox의 IoU 계산. bbox = [x1, y1, x2, y2]"""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0


class DetectorV2:
    def __init__(
        self,
        food_model: str = "yolo11s.pt",
        coco_model: str = "yolo11s.pt",
        confidence: float = 0.5,
        coco_confidence: float = 0.3,
        device: str = "cpu",
    ):
        # COCO 모델 2개 (food_model도 COCO — 파인튜닝 미사용)
        self.food_detector = YOLO(food_model)
        self.confidence = confidence
        self.device = device

        # COCO 모델 (사전필터용)
        self.coco_detector = YOLO(coco_model)
        self.coco_confidence = coco_confidence

    def _has_food_context(self, coco_boxes: list) -> bool:
        """COCO 탐지 결과에 음식 컨텍스트가 있는지 확인"""
        labels = {b["label"] for b in coco_boxes}
        return bool(labels & FOOD_CONTEXT_CLASSES)

    def _find_nearby_food_context(self, food_bbox, coco_boxes: list,
                                  iou_threshold: float = 0.0) -> bool:
        """파인튜닝 bbox 근처에 COCO 음식 컨텍스트가 있는지 확인.
        iou_threshold=0이면 겹치기만 하면 OK."""
        for cb in coco_boxes:
            if cb["label"] not in FOOD_CONTEXT_CLASSES:
                continue
            if _iou(food_bbox, cb["bbox"]) > iou_threshold:
                return True
        return False

    def infer(self, frames: list, timestamps: list) -> list:
        """
        2단계 추론:
        1) COCO 모델로 프레임 스캔 → 음식 컨텍스트 확인
        2) 컨텍스트 있는 프레임만 파인튜닝 모델 결과 채택
        """
        results = []
        for frame, ts in zip(frames, timestamps):
            # 1단계: COCO 탐지
            coco_preds = self.coco_detector(
                frame, conf=self.coco_confidence,
                device=self.device, verbose=False
            )
            coco_boxes = []
            for pred in coco_preds:
                for box in pred.boxes:
                    coco_boxes.append({
                        "label": pred.names[int(box.cls)],
                        "confidence": float(box.conf),
                        "bbox": [round(float(x), 2) for x in box.xyxy[0].tolist()],
                    })

            has_context = self._has_food_context(coco_boxes)

            # 2단계: 파인튜닝 모델 탐지
            food_preds = self.food_detector(
                frame, conf=self.confidence,
                device=self.device, verbose=False
            )

            boxes = []
            for pred in food_preds:
                for box in pred.boxes:
                    food_box = {
                        "label": pred.names[int(box.cls)],
                        "confidence": float(box.conf),
                        "bbox": [round(float(x), 2) for x in box.xyxy[0].tolist()],
                    }

                    if has_context:
                        # 메뉴명은 신뢰 X → original_label 보관, label은 food_detected
                        food_box["original_label"] = food_box["label"]
                        food_box["label"] = "food_detected"
                        food_box["context"] = "food_confirmed"
                        boxes.append(food_box)
                    else:
                        # 컨텍스트 없음 → 탈락
                        pass

            results.append({
                "frame_ts": ts,
                "boxes": boxes,
                "coco_objects": [b["label"] for b in coco_boxes],
                "food_context": has_context,
            })
        return results

    def to_records(self, vod_id: str, results: list) -> list:
        records = []
        for item in results:
            for box in item["boxes"]:
                if box["confidence"] < self.confidence:
                    continue
                records.append({
                    "vod_id":      vod_id,
                    "frame_ts":    item["frame_ts"],
                    "label":       box["label"],
                    "confidence":  box["confidence"],
                    "bbox":        box["bbox"],
                    "context":     box.get("context", ""),
                })
        return records
