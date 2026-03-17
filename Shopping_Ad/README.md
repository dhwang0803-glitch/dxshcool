# Shopping_Ad

VOD 사물인식 결과 + EPG + 상품 카탈로그 매칭 → `serving.shopping_ad` 적재

## 역할

- `Object_Detection`이 생성한 `vod_detected_object.parquet` / `vod_clip_concept.parquet` / `vod_stt_concept.parquet` 소비
- EPG(전자 프로그램 가이드) 시간표와 조인하여 방영 중 VOD 식별
- 상품 카탈로그와 매칭 → VPC `serving.shopping_ad` 테이블 적재

## 폴더 구조

```
Shopping_Ad/
├── src/          ← import 전용 라이브러리
├── scripts/      ← 직접 실행 스크립트
├── tests/        ← pytest
├── config/       ← yaml 설정
├── docs/
│   ├── plans/    ← PLAN_0X 설계 문서
│   └── reports/  ← 세션 리포트
└── data/         ← 로컬 임시 데이터 (gitignore)
```

## 실행

```bash
conda activate myenv
python scripts/run_shopping_ad.py
```
