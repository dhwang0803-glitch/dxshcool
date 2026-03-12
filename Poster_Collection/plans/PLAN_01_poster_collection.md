# PLAN_01 — Poster_Collection 구현 계획

- **작성일**: 2026-03-11
- **브랜치**: `Poster_Collection`
- **목표**: `vod` 테이블 `poster_url` 컬럼 100% 결측 → 시리즈 단위 포스터 수집·적재

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

| 항목 | 내용 | 담당 |
|------|------|------|
| `vod.poster_url` 컬럼 존재 여부 | `Database_Design` 브랜치 마이그레이션 필요 | DB 관리자 |
| Naver API 키 발급 | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` | 개발자 |
| `.env` 파일 세팅 | `config/.env.example` 참고 | 개발자 |

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

## 예상 규모 및 소요 시간

| 항목 | 추정치 |
|------|--------|
| 처리 대상 시리즈 수 | ~20,000건 (series_nm DISTINCT 기준) |
| Naver API 호출 | ~20,000회 (무료 한도 25,000/day 이내) |
| 이미지 다운로드 | ~20,000건 |
| 예상 소요 시간 | 약 1일 (API sleep 0.1초 기준) |
| 예상 로컬 저장 용량 | 약 2~5GB |

---

## 우선순위 및 구현 순서

| 순서 | 작업 | 예상 난이도 |
|:---:|------|:---:|
| 1 | `config/.env.example` 작성 | 낮음 |
| 2 | `src/naver_poster.py` 구현 + 테스트 | 중간 |
| 3 | `src/image_downloader.py` 구현 | 낮음 |
| 4 | `scripts/crawl_posters.py` 통합 | 중간 |
| 5 | `scripts/export_manifest.py` | 낮음 |
| 6 | `src/db_updater.py` + `scripts/update_poster_url.py` | 중간 |
| 7 | pytest 작성 | 낮음 |

---

## 제약 및 주의사항

- Naver 이미지 API 무료 한도: **25,000 calls/day** → 하루 1회 전체 실행 가능
- 포스터 파일은 **git 커밋 금지** (`.gitignore`: `*/posters/`, `*.jpg`, `*.png`)
- `update_poster_url.py`는 **DB 관리자만 실행**
- series_nm NULL 114건은 수집 불가 → 스킵 처리
