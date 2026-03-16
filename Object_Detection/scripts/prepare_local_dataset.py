"""
AI Hub 음식이미지 데이터 → YOLO 파인튜닝용 로컬 전처리 스크립트

[역할]
  로컬에서 이미지 리사이즈 + YOLO 변환까지 완료 후 Drive에 올릴 폴더만 생성.
  원본 100GB → 처리 후 ~3~5GB로 압축 → Drive 업로드 시간 대폭 단축.

[사전 준비]
  1. INNORIX로 로컬 다운로드
       TL.zip (142MB) — 학습 라벨
       VL.zip (18MB)  — 검증 라벨
       TS.z01 (100GB) — 학습 이미지 분할 1
  2. TS.z01을 7-Zip으로 압축 해제
       → 이미지 파일들이 있는 폴더 경로 메모

[사용법]
  conda activate myenv
  pip install opencv-python-headless pyyaml

  python scripts/prepare_local_dataset.py \
    --images-dir "C:/Users/user/Documents/AI HUB/TS" \
    --train-labels "C:/Users/user/Documents/AI HUB/TL.zip" \
    --val-labels "C:/Users/user/Documents/AI HUB/VL.zip" \
    --output-dir "C:/Users/user/Documents/AI HUB/finetune_dataset"

[출력]
  finetune_dataset/
  ├── train/
  │   ├── images/   ← 640×640 JPEG (원본 대비 ~97% 용량 감소)
  │   └── labels/   ← YOLO .txt (class_id cx cy w h)
  ├── val/
  │   ├── images/
  │   └── labels/
  └── data.yaml

  → finetune_dataset/ 폴더를 Drive에 업로드
  → Colab Step 3(data.yaml 확인) → Step 4(학습) 바로 실행
"""

import argparse
import json
import os
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path

import cv2
import yaml

TARGET_SIZE = 640
JPEG_QUALITY = 85


# ── 유틸리티 ──────────────────────────────────────────────────────────────────

def extract_zip(zip_path: str, dest_dir: str):
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    print(f"  압축 해제: {Path(zip_path).name} → {dest_dir}")
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(dest_dir)
    print("  완료")


def collect_classes(label_dir: str):
    """JSON food_type.fc 전체 스캔 → 클래스 목록 (빈도 내림차순)"""
    json_files = list(Path(label_dir).rglob('*.json'))
    print(f"  JSON {len(json_files):,}개 스캔 중...")

    class_count = defaultdict(int)
    errors = 0
    for jf in json_files:
        try:
            with open(jf, encoding='utf-8') as f:
                d = json.load(f)
            fc = d.get('data', {}).get('food_type', {}).get('fc', '').strip()
            if fc:
                class_count[fc] += 1
        except Exception:
            errors += 1

    sorted_cls = sorted(class_count.items(), key=lambda x: -x[1])
    names = [c for c, _ in sorted_cls]
    print(f"  클래스: {len(names)}종 / 파싱 오류: {errors}개")
    print("  상위 10개:", [c for c, _ in sorted_cls[:10]])
    return names, {c: i for i, c in enumerate(names)}


def build_image_index(images_dir: str) -> dict:
    """파일명 → 절대경로 인덱스 (대소문자 통일)"""
    print(f"  이미지 인덱스 구축: {images_dir}")
    index = {}
    for ext in ('*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG'):
        for p in Path(images_dir).rglob(ext):
            index[p.name.lower()] = str(p)
    print(f"  {len(index):,}장 인덱싱 완료")
    return index


# ── 핵심 변환 ─────────────────────────────────────────────────────────────────

def convert_one(json_path: str, image_index: dict, class_to_id: dict,
                out_img_dir: str, out_lbl_dir: str) -> bool:
    """
    JSON 1개 처리:
      - 이미지 로드 → 640×640 리사이즈 → JPEG 저장
      - bbox → YOLO 정규화 좌표 → .txt 저장
    """
    try:
        with open(json_path, encoding='utf-8') as f:
            raw = json.load(f)
        d = raw.get('data', {})

        fc = d.get('food_type', {}).get('fc', '').strip()
        if not fc or fc not in class_to_id:
            return False

        ii = d.get('image_info', {})
        fname = ii.get('file_name', '')
        iw = float(ii.get('width', 0))
        ih = float(ii.get('height', 0))
        if not fname or iw <= 0 or ih <= 0:
            return False

        src_path = image_index.get(fname.lower())
        if not src_path:
            return False

        a = d.get('2d_annotation', {})
        x  = float(a.get('x', 0))
        y  = float(a.get('y', 0))
        bw = float(a.get('width', 0))
        bh = float(a.get('height', 0))
        if bw <= 0 or bh <= 0:
            return False

        # YOLO 정규화 좌표 (원본 크기 기준)
        cx = (x + bw / 2) / iw
        cy = (y + bh / 2) / ih
        nw = bw / iw
        nh = bh / ih
        if not all(0.0 < v <= 1.0 for v in [cx, cy, nw, nh]):
            return False

        # 이미지 로드 + 리사이즈
        img = cv2.imread(src_path)
        if img is None:
            return False
        img_resized = cv2.resize(img, (TARGET_SIZE, TARGET_SIZE),
                                 interpolation=cv2.INTER_AREA)

        # 저장
        stem = Path(fname).stem
        cv2.imwrite(
            str(Path(out_img_dir) / f"{stem}.jpg"),
            img_resized,
            [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
        )
        Path(out_lbl_dir, f"{stem}.txt").write_text(
            f"{class_to_id[fc]} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}\n",
            encoding='utf-8'
        )
        return True

    except Exception:
        return False


def process_split(label_dir: str, image_index: dict, class_to_id: dict,
                  out_base: str, split: str) -> int:
    json_files = list(Path(label_dir).rglob('*.json'))
    print(f"\n[{split}] {len(json_files):,}개 변환 중...")

    out_img = Path(out_base) / split / 'images'
    out_lbl = Path(out_base) / split / 'labels'
    out_img.mkdir(parents=True, exist_ok=True)
    out_lbl.mkdir(parents=True, exist_ok=True)

    ok = skip = 0
    for i, jf in enumerate(json_files):
        if i % 500 == 0:
            pct = i / len(json_files) * 100
            print(f"  {pct:.1f}% ({i:,}/{len(json_files):,}) 성공:{ok:,} 실패:{skip:,}",
                  end='\r')
        if convert_one(str(jf), image_index, class_to_id,
                       str(out_img), str(out_lbl)):
            ok += 1
        else:
            skip += 1

    print(f"\n  [{split}] 완료 — 성공: {ok:,} / 실패(이미지없음·bbox오류): {skip:,}")
    return ok


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='AI Hub 음식이미지 → YOLO 로컬 전처리 (Drive 업로드 용량 최소화)'
    )
    BASE = r'C:\Users\user\Documents\AI HUB'
    parser.add_argument('--images-dir',
                        default=rf'{BASE}\TS',
                        help='TS.z01 압축 해제 폴더 (기본: AI HUB\\TS)')
    parser.add_argument('--train-labels',
                        default=rf'{BASE}\TL.zip',
                        help='TL.zip 경로 (기본: AI HUB\\TL.zip)')
    parser.add_argument('--val-labels',
                        default=rf'{BASE}\VL.zip',
                        help='VL.zip 경로 (기본: AI HUB\\VL.zip)')
    parser.add_argument('--output-dir',
                        default=rf'{BASE}\finetune_dataset',
                        help='출력 폴더 (기본: AI HUB\\finetune_dataset)')
    parser.add_argument('--skip-extract',  action='store_true',
                        help='라벨 압축 해제 이미 완료 시 스킵')
    args = parser.parse_args()

    out = Path(args.output_dir)
    tmp = out / '_tmp_labels'

    print("=" * 50)
    print("AI Hub → YOLO 로컬 전처리")
    print("=" * 50)

    # 1. 학습 라벨 압축 해제
    tl_dir = str(tmp / 'train_labels')
    if args.skip_extract and Path(tl_dir).exists():
        print(f"\n[스킵] 학습 라벨 압축 해제 (--skip-extract)")
    else:
        print("\n[1] 학습 라벨 압축 해제")
        extract_zip(args.train_labels, tl_dir)

    # 2. 클래스 수집
    print("\n[2] 클래스 수집")
    all_classes, class_to_id = collect_classes(tl_dir)

    # 3. 이미지 인덱스
    print("\n[3] 이미지 인덱스 구축")
    image_index = build_image_index(args.images_dir)

    # 4. train 변환
    print("\n[4] 학습 데이터 변환 (640×640 리사이즈 + YOLO 포맷)")
    train_n = process_split(tl_dir, image_index, class_to_id, str(out), 'train')

    # 5. val 변환 (있으면)
    val_n = 0
    if args.val_labels and Path(args.val_labels).exists():
        print("\n[5] 검증 데이터 변환")
        vl_dir = str(tmp / 'val_labels')
        if not (args.skip_extract and Path(vl_dir).exists()):
            extract_zip(args.val_labels, vl_dir)
        val_n = process_split(vl_dir, image_index, class_to_id, str(out), 'val')
    else:
        print("\n[5] VL.zip 없음 — val 스킵 (Colab에서 학습 데이터 80:20 분리)")

    # 6. data.yaml
    yaml_path = out / 'data.yaml'
    with open(yaml_path, 'w', encoding='utf-8') as f:
        yaml.dump({
            'train': './train/images',
            'val':   './val/images',
            'nc':    len(all_classes),
            'names': all_classes,
        }, f, allow_unicode=True, default_flow_style=False)

    # 7. tmp 정리
    shutil.rmtree(str(tmp), ignore_errors=True)

    # 8. 결과 요약
    size_bytes = sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
    size_gb = size_bytes / 1e9
    size_mb = size_bytes / 1e6

    print(f"""
{'=' * 50}
완료
{'=' * 50}
출력 폴더  : {out}
train      : {train_n:,}장
val        : {val_n:,}장
클래스     : {len(all_classes)}종
폴더 크기  : {size_gb:.1f} GB ({size_mb:,.0f} MB)  ← Drive 업로드 대상

다음 단계:
  1. {out} 폴더를 Drive에 업로드
       C:\\Users\\user\\Documents\\AI HUB\\finetune_dataset
       → Drive > LGHellovision > Project 02 > Object Detection > finetune_dataset
  2. Colab Step 3 (data.yaml 확인) → Step 4 (학습 시작)
     → Step 1~2 (클래스 스캔 + 변환)는 이 스크립트가 대신 처리했으므로 스킵
{'=' * 50}
""")


if __name__ == '__main__':
    main()
