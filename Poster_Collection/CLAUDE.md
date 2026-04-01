# Poster_Collection — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

**TMDB/Tving에서 시리즈별 포스터·백드롭 이미지를 수집하여 DB의 `poster_url`/`backdrop_url` 컬럼을 채운다.**

전체 워크플로우는 개발자(크롤링·로컬 저장)와 DB 관리자(OCI 업로드·DB 적재)로 역할이 나뉜다.

**이미지 서빙 아키텍처**: API 서버는 `poster_url`(문자열)만 반환. 이미지 자체는 브라우저가 OCI Object Storage에서 직접 다운로드.
VPC 컴퓨트 인스턴스에 이미지 트래픽이 전혀 없음 (페이지당 200포스터 x 80KB = 16MB를 Object Storage가 담당).

```
[개발자]
  1. TMDB search → 시리즈별 포스터 URL 수집 (ct_cl 기반 movie/tv 분기)
  2. Tving 사이트맵 인덱스 → TMDB 미매칭 시 폴백
  3. 이미지 다운로드 → 로컬 저장
  4. 매니페스트 CSV 생성 (series_id, series_nm, season, local_path, poster_url)

[DB 관리자]
  5. upload_to_oci.py 실행 → OCI Object Storage 업로드
     (--update-db 옵션으로 DB 자동 반영 가능)

[프론트엔드]
  6. API 서버 → poster_url JSON 반환
  7. 브라우저 → OCI에서 이미지 직접 다운로드
```

## 파일 위치 규칙 (MANDATORY)

```
Poster_Collection/
├── src/                ← import 전용 라이브러리 (직접 실행 X)
│   ├── tmdb_poster.py        # TMDB search/movie·search/tv → 포스터 URL (시즌 포스터 지원)
│   ├── tving_poster.py       # Tving 사이트맵 인덱스 → og:image 매칭 (TMDB 폴백)
│   ├── image_downloader.py   # URL → 로컬 파일 다운로드
│   ├── db_updater.py         # DB poster_url UPDATE (관리자용)
│   └── oci_uploader.py       # OCI Object Storage 업로드
├── scripts/            ← 직접 실행 스크립트
│   ├── crawl_posters.py           # 포스터 크롤링 메인 (TMDB+Tving, 시리즈×시즌 단위)
│   ├── crawl_backdrops.py         # TMDB 백드롭(가로) 크롤링 → OCI → backdrop_url UPDATE
│   ├── run_full_pipeline.py       # 4분할 병렬 크롤링 → manifest 통합 → OCI → DB 일괄
│   ├── build_tving_index.py       # Tving 사이트맵 인덱스 1회 빌드
│   ├── export_manifest.py         # 매니페스트 CSV 생성
│   ├── upload_to_oci.py           # OCI 업로드 + DB 반영 (--update-db)
│   ├── verify_tmdb_matches.py     # TMDB 매칭 정확도 검증
│   ├── fix_series_nm_collision.py # series_nm 충돌 수정
│   └── fix_serving_posters.py     # 서빙 테이블 포스터 일괄 교체
├── tests/              ← pytest
│   └── test_image_downloader.py
├── config/             ← 설정
│   └── tving_index.json    # Tving 사이트맵 캐시 (build_tving_index.py 생성)
├── plans/              ← 설계 문서
│   └── PLAN_01_poster_collection.md
├── reports/            ← 파일럿 결과
└── docs/               ← (비어있음)
```

**`Poster_Collection/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
import requests                  # TMDB API / 이미지 다운로드
from difflib import SequenceMatcher  # 제목 유사도 매칭
import psycopg2                  # DB poster_url 업데이트
from dotenv import load_dotenv
```

포스터 소스:
- **TMDB** (1순위): `search/movie` · `search/tv` → `poster_path` (ct_cl 기반 분기)
  - TV 시리즈: `/tv/{id}` → `seasons[].poster_path` 시즌 포스터 획득
- **Tving** (폴백): 사이트맵 크롤링 → `title→og:image` 인덱스 매칭

## 파이프라인 실행

```bash
# 1. (최초 1회) Tving 사이트맵 인덱스 빌드
python Poster_Collection/scripts/build_tving_index.py

# 2. 포스터 크롤링 (단일)
python Poster_Collection/scripts/crawl_posters.py              # 전체
python Poster_Collection/scripts/crawl_posters.py --limit 100  # 테스트
python Poster_Collection/scripts/crawl_posters.py --resume     # 재개

# 3. 전체 파이프라인 (4분할 병렬 크롤링 → 통합 → OCI → DB)
python Poster_Collection/scripts/run_full_pipeline.py
python Poster_Collection/scripts/run_full_pipeline.py --skip-crawl  # 통합부터
python Poster_Collection/scripts/run_full_pipeline.py --dry-run     # 확인만

# 4. 백드롭(가로 이미지) 크롤링
python Poster_Collection/scripts/crawl_backdrops.py
python Poster_Collection/scripts/crawl_backdrops.py --dry-run

# 5. OCI 업로드 (관리자)
python Poster_Collection/scripts/upload_to_oci.py --update-db

# 6. 검증/수정
python Poster_Collection/scripts/verify_tmdb_matches.py
python Poster_Collection/scripts/fix_series_nm_collision.py
python Poster_Collection/scripts/fix_serving_posters.py
```

## 인터페이스

> 컬럼/타입 상세 → `Database_Design/docs/DEPENDENCY_MAP.md` Poster_Collection 섹션 참조 (Rule 1).
> 스키마 변경 시 Database_Design 기준으로 이 섹션도 업데이트할 것 (Rule 3).

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.vod` | `full_asset_id` | VARCHAR(64) | VOD 식별 |
| `public.vod` | `series_nm` | VARCHAR | 시리즈 단위 크롤링 기준 |
| `public.vod` | `asset_nm` | VARCHAR | 시즌 번호 파싱 (`parse_season_from_asset_nm`) |
| `public.vod` | `ct_cl` | VARCHAR(64) | TMDB media_type 분기 (영화/TV) |
| `public.vod` | `poster_url` | TEXT | `IS NULL` 조건 — 수집 대상 필터 |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `public.vod` | `poster_url` | TEXT | OCI Object Storage URL |
| `public.vod` | `backdrop_url` | TEXT | TMDB 백드롭 → OCI URL (crawl_backdrops.py) |

## 환경변수

```bash
# .env 필수 항목
TMDB_API_KEY=              # TMDB v3 API
TMDB_READ_ACCESS_TOKEN=    # TMDB Bearer token
LOCAL_POSTER_DIR=          # 로컬 포스터 저장 경로
DB_HOST=
DB_PORT=5432
DB_NAME=
DB_USER=
DB_PASSWORD=

# OCI Object Storage (관리자 전용)
OCI_NAMESPACE=
OCI_BUCKET_NAME=vod-posters
OCI_REGION=
OCI_CONFIG_PROFILE=DEFAULT
```

## 주의사항 (MANDATORY)

1. **포스터 파일을 git에 커밋하지 않는다** — `.gitignore` 필수
2. `LOCAL_POSTER_DIR`는 반드시 `os.getenv()` 로 읽는다 (하드코딩 금지)
3. TMDB API 키는 `.env`에서만 로드한다
4. DB UPDATE는 관리자만 실행 (팀원은 crawl + export까지만)

---

**마지막 수정**: 2026-04-01
**프로젝트 상태**: 파이프라인 구현 완료, TMDB+Tving 소스 운영 중
