# Task B 완료 보고서 — TV 연예/오락 CLIP 영상 임베딩

- **작성일**: 2026-03-13
- **담당**: Task B (TV 연예/오락)
- **브랜치**: `VOD_Embedding`

---

## 작업 개요

| 항목 | 내용 |
|------|------|
| 담당 범위 | TV 연예/오락 (full_asset_id 정렬 뒤 절반) |
| 작업 파일 | `data/tasks_B.json` |
| 총 대상 | 9,571건 |
| 작업 시작 | 2026-03-11 |
| 작업 완료 | 2026-03-13 |

---

## PLAN_01 — 트레일러 크롤링 결과

| 항목 | 수치 |
|------|------|
| 처리 | 9,659건 |
| 성공 | 9,568건 |
| 실패 | 91건 (실패율 0.9%) |
| 실패 원인 | YouTube 미등재 콘텐츠 |
| 주요 실패 시리즈 | 안싸우면 다행이야(18), 아는 형님(17), 갬성캠핑(10), 엔시티 월드 2.0(5) 등 |

---

## PLAN_02 — CLIP 임베딩 결과

| 항목 | 수치 |
|------|------|
| 처리 대상 | 735개 파일 (성공 크롤링 기준) |
| 성공 | 8,729건 |
| 실패 | 40건 (손상된 mp4, partial file) |
| 임베딩 모델 | CLIP ViT-B/32 |
| 벡터 차원 | 512차원 |
| 프레임 추출 | 영상당 10프레임 균등 추출 후 평균 벡터 |

---

## 산출물

| 파일 | 위치 | 크기 | 비고 |
|------|------|------|------|
| `embeddings_B.parquet` | `data/embeddings_B.parquet` | 4.6MB | Google Drive 별도 전달 |

- parquet 컬럼: `vod_id`, `embedding` (512차원 float32)
- 압축 방식: snappy (비압축 시 약 17.9MB)

---

## 사후 영향 평가

| 항목 | 내용 |
|------|------|
| 영향 테이블 | `public.vod_embedding` (쓰기, 오너 적재 후) |
| 영향 브랜치 | `Vector_Search`, `User_Embedding`, `CF_Engine` |
| 리스크 등급 | 🟡 MEDIUM — 코드 변경만, DB 적재는 오너 별도 실행 |
| 하위 호환성 | `ON CONFLICT (vod_id_fk) DO UPDATE` 멱등성 보장 |
| 대용량 데이터 | `.gitignore`로 parquet/영상/체크포인트 제외 확인 완료 |

---

## 보안 점검 보고서

| 항목 | 결과 |
|------|------|
| 하드코딩된 자격증명 | ✅ 없음 — DB 접속 정보 `os.getenv()` 사용 |
| `os.getenv()` 기본값 | ✅ 실제 인프라 정보 기본값 없음 |
| `.env` 커밋 여부 | ✅ `.gitignore` 포함 확인 |
| 대용량 데이터 커밋 | ✅ `data/` 폴더 `.gitignore` 처리 완료 |
| API 키 노출 | ✅ 없음 |

---

## 다음 단계

- `embeddings_B.parquet` → Google Drive 업로드 → 조장 전달
- 조장이 `ingest_to_db.py` 실행 → `public.vod_embedding` 테이블 적재
- DB 적재 완료 후 `Vector_Search` 브랜치 작업 시작
