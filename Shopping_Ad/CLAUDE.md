# Shopping_Ad — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

**VOD 사물인식 결과 + EPG + 상품 카탈로그 매칭** — Object_Detection의 parquet 산출물을 소비하여
쇼핑 광고 팝업 데이터를 생성하고 VPC `serving.shopping_ad` 테이블에 적재한다.

### 데이터 플로우

```
[Object_Detection 산출물]
  vod_detected_object.parquet   ← YOLO bbox 탐지 결과
  vod_clip_concept.parquet      ← CLIP 개념 태깅 결과
  vod_stt_concept.parquet       ← Whisper STT 키워드 결과
        ↓
  [Shopping_Ad]
  EPG 시간표 조인 → 방영 중 VOD 식별
  상품 카탈로그 매칭 → ad_category / 상품 후보 생성
  신뢰도 필터링 + context_valid 체크
        ↓
  serving.shopping_ad (VPC)     ← API_Server가 소비
```

---

## 파일 위치 규칙 (MANDATORY)

```
Shopping_Ad/
├── src/          ← import 전용 라이브러리 (직접 실행 X)
├── scripts/      ← 직접 실행 스크립트
├── tests/        ← pytest
├── config/       ← yaml 설정
│   └── ad_config.yaml
└── docs/
    ├── plans/    ← PLAN_0X 설계 문서
    └── reports/  ← 세션 리포트
```

**`Shopping_Ad/` 루트에 `.py` 파일 직접 생성 금지.**

---

## 인터페이스

> 컬럼/타입 상세 → `Database_Design/docs/DEPENDENCY_MAP.md` 참조 (Rule 1).

### 업스트림 (읽기)

| 소스 | 컬럼/항목 | 타입 | 용도 |
|------|----------|------|------|
| `vod_detected_object.parquet` | `vod_id`, `frame_ts`, `label`, `confidence`, `bbox` | str/float/str/float/list | YOLO 탐지 결과 소비 |
| `vod_clip_concept.parquet` | `vod_id`, `frame_ts`, `concept`, `clip_score`, `ad_category`, `context_valid` | str/float/str/float/str/bool | CLIP 개념 소비 |
| `vod_stt_concept.parquet` | `vod_id`, `start_ts`, `end_ts`, `transcript`, `keyword`, `ad_category`, `ad_hints` | str/float/float/str/str/str/list | STT 키워드 소비 |
| `public.vod` | `full_asset_id`, `asset_nm` | VARCHAR(64), VARCHAR | VOD 메타데이터 |

### 다운스트림 (쓰기)

| 대상 | 컬럼 | 타입 | 비고 |
|------|------|------|------|
| `serving.shopping_ad` (VPC) | *(스키마 미확정)* | - | Database_Design과 협의 후 확정 |

> `serving.shopping_ad` 스키마는 Database_Design 담당자와 협의 후 확정.

---

## 실행 환경

```bash
conda activate myenv
pip install pandas pyarrow psycopg2-binary pyyaml
```

---

## 협업 규칙

- `main` 브랜치 직접 Push 금지 — 반드시 PR
- Object_Detection parquet 스키마 변경 시 이 파일 인터페이스 섹션 업데이트
- `serving.shopping_ad` 스키마 확정 전까지 DB 직접 적재 구현 보류
