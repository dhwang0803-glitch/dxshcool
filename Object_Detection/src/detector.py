"""
detector.py — YOLOv11/v8 추론 래퍼
"""
from ultralytics import YOLO


class Detector:
    def __init__(self, model_name: str = "yolo11s.pt", confidence: float = 0.5, device: str = "cpu"):
        self.model = YOLO(model_name)
        self.confidence = confidence
        self.device = device

    def infer(self, frames: list, timestamps: list) -> list:
        """
        프레임 배열 → YOLO 추론 결과 반환.

        Returns:
            list of {"frame_ts": float, "boxes": [...]}
        """
        results = []
        for frame, ts in zip(frames, timestamps):
            preds = self.model(frame, conf=self.confidence, device=self.device, verbose=False)
            boxes = []
            for pred in preds:
                for box in pred.boxes:
                    boxes.append({
                        "label": pred.names[int(box.cls)],
                        "confidence": float(box.conf),
                        "bbox": [round(float(x), 2) for x in box.xyxy[0].tolist()],
                    })
            results.append({"frame_ts": ts, "boxes": boxes})
        return results

    def to_records(self, vod_id: str, results: list) -> list:
        """
        추론 결과 → parquet 행 리스트 변환.

        Returns:
            list of {"vod_id", "frame_ts", "label", "confidence", "bbox"}
        """
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
                })
        return records
