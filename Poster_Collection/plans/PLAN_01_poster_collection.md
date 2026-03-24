# PLAN_01 — Poster_Collection 구현 계획

- **작성일**: 2026-03-11
- **최종 수정**: 2026-03-12 (파일럿 결과 반영)
- **브랜치**: `Poster_Collection`
- **목표**: `vod` 테이블 `poster_url` 컬럼 100% 결측 → 시리즈 단위 포스터 수집·적재
- **현재 상태**: Phase 0 완료 · Phase 1~2 구현 완료 · 파일럿 테스트 완료

---

## 현황

| 항목 | 수치 |
|------|------|
| 전체 VOD 레코드 | 166,159건 |
| `poster_url` 결측 | 166,159건 (100%) |
| 처리 단위 | `series_nm` 기준 시리즈 (중복 제거 후 약 수천~수만 시리즈 예상) |

---

## 워크플로우 개요

```
[개발자]
  Step 1. vod 테이블에서 poster_url IS NULL인 series_nm 목록 조회
  Step 2. series_nm → Naver 이미지 API 검색 → 최적 포스터 URL 선택
  Step 3. 이미지 다운로드 → 로컬 {LOCAL_POSTER_DIR}/{series_id}.jpg 저장
  Step 4. 매니페스트 CSV 생성 (series_id, series_nm, local_path, naver_url)
  Step 5. Google Drive로 DB 관리자에게 전달

[DB 관리자]
  Step 6. Google Drive → VPC 서버 업로드
  Step 7. update_poster_url.py 실행 → vod.poster_url UPDATE
```

---

## 구현 단계

### Phase 0. 선행 조건 확인

| 항목 | 내용 | 상태 |
|------|------|------|
| `vod.poster_url` 컬럼 존재 여부 | `Database_Design` 브랜치 `20260311_add_poster_url_to_vod.sql` 마이그레이션 완료 | ✅ 완료 |
| Naver API 키 발급 | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | ✅ 완료 |
| `.env` 파일 세팅 | `config/.env.example` 참고 | ✅ 완료 |

```sql
-- Database_Design 브랜치에서 선행 실행 필요
ALTER TABLE vod ADD COLUMN IF NOT EXISTS poster_url TEXT;
```

---

### Phase 1. `src/naver_poster.py` 구현

**역할**: Naver 이미지 API로 시리즈별 포스터 URL 수집

```
입력: series_nm (str)
출력: 포스터 이미지 URL (str) 또는 None

핵심 로직:
  1. Naver 이미지 검색 API 호출
     GET https://openapi.naver.com/v1/search/image
     params: query="{series_nm} 포스터", display=5, filter=large
  2. 결과 중 poster 적합도 필터링
     - 세로형 이미지 우선 (height > width)
     - 제목 유사도 검사 (series_nm이 link/title에 포함)
  3. 최적 URL 반환 (없으면 None)
```

**Rate Limit 대응**:
- API 호출 간 `time.sleep(0.1)` (Naver 무료 API: 25,000 calls/day)
- 실패 시 최대 3회 재시도 (exponential backoff)

---

### Phase 2. `src/image_downloader.py` 구현

**역할**: 포스터 URL → 로컬 이미지 파일 저장

```
입력: series_id (int), poster_url (str), local_dir (str)
출력: local_path (str) 또는 None

핵심 로직:
  1. requests.get(poster_url, timeout=10)
  2. Content-Type 검증 (image/jpeg, image/png, image/webp)
  3. {local_dir}/{series_id}.jpg 저장
  4. 실패 시 None 반환 (프로세스 중단 없이 계속)
```

---

### Phase 3. `src/db_updater.py` 구현

**역할**: 매니페스트 CSV + VPC 경로 → `vod.poster_url` UPDATE (관리자 전용)

```
입력: manifest CSV, vpc_path_mapping CSV
출력: 업데이트 건수 로그

핵심 로직:
  UPDATE vod
  SET poster_url = %s, updated_at = NOW()
  WHERE series_id = %s AND poster_url IS NULL
```

---

### Phase 4. `scripts/crawl_posters.py` 구현

**역할**: Phase 1~2 통합 실행 스크립트

```
실행 흐름:
  1. DB에서 poster_url IS NULL인 series 목록 조회
     SELECT DISTINCT series_id, series_nm FROM vod
     WHERE poster_url IS NULL AND series_nm IS NOT NULL
  2. 각 series에 대해:
     a. naver_poster.search(series_nm) → poster_url
     b. image_downloader.download(series_id, poster_url) → local_path
     c. 결과 매니페스트 누적
  3. 체크포인트: 매 50건마다 crawl_status.json 저장 (중단 재개 가능)
  4. 완료 후 manifest CSV 저장
```

**실행 옵션**:
```bash
python scripts/crawl_posters.py                    # 전체 실행
python scripts/crawl_posters.py --limit 100        # 테스트용 100건
python scripts/crawl_posters.py --resume           # 체크포인트 재개
```

---

### Phase 5. `scripts/export_manifest.py` 구현

**역할**: 수집 결과 → Google Drive 전달용 CSV 생성

```csv
series_id,series_nm,local_path,naver_url,downloaded_at
10001,이상한변호사우영우,/posters/10001.jpg,https://...,2026-03-11
```

---

### Phase 6. `scripts/update_poster_url.py` 구현 (관리자 전용)

**역할**: VPC 업로드 완료 후 DB poster_url 일괄 업데이트

```bash
python scripts/update_poster_url.py --manifest manifest.csv --vpc-map vpc_paths.csv
```

---

## 파일 구조 (완성 목표)

```
Poster_Collection/
├── src/
│   ├── naver_poster.py       ← Naver API 검색
│   ├── image_downloader.py   ← 이미지 다운로드
│   └── db_updater.py         ← DB poster_url 업데이트
├── scripts/
│   ├── crawl_posters.py      ← 메인 크롤링 실행
│   ├── export_manifest.py    ← CSV 매니페스트 생성
│   └── update_poster_url.py  ← DB 업데이트 (관리자)
├── tests/
│   ├── test_naver_poster.py
│   └── test_image_downloader.py
├── config/
│   └── .env.example
├── plans/
│   └── PLAN_01_poster_collection.md  ← 이 문서
└── reports/
```

---

## 환경변수 (`.env`)

```bash
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
LOCAL_POSTER_DIR=          # 예: C:/Users/user/Desktop/posters
DB_HOST=
DB_PORT=5432
DB_NAME=
DB_USER=
DB_PASSWORD=
```

---

## 파일럿 결과 (2026-03-12, 50건 기준)

> `scripts/pilot_test.py --limit 50 --save-report` 실행 결과

| 지표 | 수치 |
|------|------|
| Naver API 성공률 | **100.0%** |
| 이미지 다운로드 성공률 | **94.0%** |
| portrait 이미지 비율 | **96.0%** |
| 처리 속도 | **53.9건/분** (1.112초/건) |
| 전체 20,000건 예상 소요 시간 | **약 6.2시간** |

- 리포트: `reports/pilot_01_20260312_150353.json`

---

## 예상 규모 및 소요 시간 (파일럿 실측 반영)

| 항목 | 추정치 |
|------|--------|
| 처리 대상 시리즈 수 | ~20,000건 (series_nm DISTINCT 기준) |
| Naver API 호출 | ~20,000회 (무료 한도 25,000/day 이내) |
| 이미지 다운로드 | ~18,800건 (다운로드 성공률 94% 기준) |
| 예상 소요 시간 | **약 6.2시간** (파일럿 실측: 1.112초/건) |
| 예상 로컬 저장 용량 | 약 2~5GB |

---

## 우선순위 및 구현 순서

| 순서 | 작업 | 상태 |
|:---:|------|:---:|
| 1 | `config/.env.example` 작성 | ✅ 완료 |
| 2 | `src/naver_poster.py` 구현 | ✅ 완료 |
| 3 | `src/image_downloader.py` 구현 | ✅ 완료 |
| 3.5 | `scripts/pilot_test.py` 파일럿 검증 | ✅ 완료 |
| 4 | `scripts/crawl_posters.py` 통합 | 🔲 미구현 |
| 5 | `scripts/export_manifest.py` | 🔲 미구현 |
| 6 | `src/db_updater.py` + `scripts/update_poster_url.py` | 🔲 미구현 |
| 7 | pytest 작성 | 🔲 미구현 |

---

## 제약 및 주의사항

- Naver 이미지 API 무료 한도: **25,000 calls/day** → 하루 1회 전체 실행 가능
- 포스터 파일은 **git 커밋 금지** (`.gitignore`: `*/posters/`, `*.jpg`, `*.png`)
- `update_poster_url.py`는 **DB 관리자만 실행**
- series_nm NULL 114건은 수집 불가 → 스킵 처리
