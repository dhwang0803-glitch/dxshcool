"""
train 데이터 80:20 분리 → val 생성

사용법:
  python Object_Detection/scripts/split_val.py

기본 경로: C:\\Users\\user\\Documents\\AI HUB\\finetune_dataset
"""

import random
import shutil
from pathlib import Path

DATASET_DIR = r'C:\Users\user\Documents\AI HUB\finetune_dataset'
VAL_RATIO   = 0.2
SEED        = 42


def main():
    train_img_dir = Path(DATASET_DIR) / 'train' / 'images'
    train_lbl_dir = Path(DATASET_DIR) / 'train' / 'labels'
    val_img_dir   = Path(DATASET_DIR) / 'val'   / 'images'
    val_lbl_dir   = Path(DATASET_DIR) / 'val'   / 'labels'

    val_img_dir.mkdir(parents=True, exist_ok=True)
    val_lbl_dir.mkdir(parents=True, exist_ok=True)

    images = list(train_img_dir.glob('*.jpg'))
    print(f"train 이미지: {len(images):,}장")

    random.seed(SEED)
    random.shuffle(images)
    n_val = int(len(images) * VAL_RATIO)
    val_images = images[:n_val]

    print(f"val 이동: {n_val:,}장 ({VAL_RATIO*100:.0f}%)")

    moved = 0
    for img_path in val_images:
        lbl_path = train_lbl_dir / (img_path.stem + '.txt')
        if not lbl_path.exists():
            continue
        shutil.move(str(img_path), val_img_dir / img_path.name)
        shutil.move(str(lbl_path), val_lbl_dir / lbl_path.name)
        moved += 1

    train_remaining = len(list(train_img_dir.glob('*.jpg')))
    val_final       = len(list(val_img_dir.glob('*.jpg')))

    print(f"\n완료")
    print(f"  train: {train_remaining:,}장")
    print(f"  val:   {val_final:,}장")


if __name__ == '__main__':
    main()
