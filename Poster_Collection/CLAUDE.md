# Poster_Collection — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

**Naver에서 시리즈별 포스터 이미지를 수집하여 DB의 `poster_url` 컬럼을 채운다.**

전체 워크플로우는 개발자(크롤링·로컬 저장)와 DB 관리자(VPC 업로드·DB 적재)로 역할이 나뉜다.

```
[개발자]
  1. Naver 검색 → 시리즈별 포스터 URL 수집
  2. 이미지 다운로드 → 로컬 저장
  3. 매니페스트 CSV 생성 (series_id, local_path, naver_url)
  4. Google Drive로 관리자에게 전달

[DB 관리자]
  5. Google Drive → VPC 서버에 이미지 업로드
  6. VPC 경로 확정 후 update_poster_url.py 실행
  7. vod 테이블 poster_url 컬럼 업데이트
```

## 파일 위치 규칙 (MANDATORY)

```
Poster_Collection/
├── src/       ← import 전용 라이브러리 (직접 실행 X)
├── scripts/   ← 직접 실행 스크립트 (python scripts/xxx.py)
├── tests/     ← pytest
├── config/    ← 설정 yaml
├── plans/     ← PLAN_0X 설계 문서
└── reports/   ← 파일럿 결과 리포트
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| Naver 포스터 URL 수집 라이브러리 | `src/naver_poster.py` |
| 이미지 다운로드·로컬 저장 라이브러리 | `src/image_downloader.py` |
| DB poster_url 업데이트 라이브러리 | `src/db_updater.py` |
| 포스터 크롤링 실행 스크립트 | `scripts/crawl_posters.py` |
| Google Drive 전달용 매니페스트 생성 | `scripts/export_manifest.py` |
| DB poster_url 업데이트 (관리자용) | `scripts/update_poster_url.py` |
| pytest | `tests/` |
| 크롤링 설정 | `config/poster_config.yaml` |

**`Poster_Collection/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
import requests                  # Naver 검색 API / HTTP 요청
from bs4 import BeautifulSoup    # HTML 파싱 (API 미제공 시 폴백)
import psycopg2                  # DB poster_url 업데이트
from dotenv import load_dotenv
import csv                       # 매니페스트 생성
```

Naver 검색 API:
- 이미지 검색 API: `https://openapi.naver.com/v1/search/image`
- 헤더: `X-Naver-Client-Id`, `X-Naver-Client-Secret` (환경변수 로드)

## 수집 파이프라인 상세

### crawl_posters.py 흐름

```
vod 테이블에서 poster_url IS NULL인 series 목록 조회
    → series_nm 기반 Naver 이미지 API 검색
    → 결과 중 가장 적합한 이미지 URL 선택 (유사도 필터링)
    → 이미지 다운로드 → {LOCAL_POSTER_DIR}/{series_id}.jpg 저장
    → 매니페스트 CSV 누적 기록
```

### export_manifest.py 출력 형식

```csv
series_id,series_nm,local_path,naver_url,downloaded_at
10001,이상한변호사우영우,/posters/10001.jpg,https://...,2026-03-11
...
```

### update_poster_url.py 흐름 (관리자 전용)

```
manifest CSV + VPC 업로드 완료 경로 매핑 파일 수신
    → series_id 기준 vod 테이블 poster_url UPDATE
    → 업데이트 건수 로그 출력
```

## 환경변수

```bash
# .env 필수 항목
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
LOCAL_POSTER_DIR=/path/to/local/posters   # 팀원 로컬 경로
DB_HOST=...
DB_PORT=5432
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
```

## 주의사항 (MANDATORY)

1. **포스터 파일을 git에 커밋하지 않는다** — `.gitignore` 필수 항목:
   ```
   */posters/
   *.jpg
   *.jpeg
   *.png
   ```
2. `LOCAL_POSTER_DIR`는 반드시 `os.getenv("LOCAL_POSTER_DIR")` 로 읽는다 (하드코딩 금지)
3. Naver API 키는 `.env`에서만 로드한다
4. `update_poster_url.py`는 DB 관리자만 실행한다 (팀원은 crawl + export까지만)

## DB 스키마 변경 (Database_Design 브랜치 필요)

이 모듈 작업 전에 Database_Design 브랜치에서 아래 마이그레이션이 선행되어야 한다:

```sql
-- Database_Design/migrations/ 에 추가
ALTER TABLE vod ADD COLUMN poster_url TEXT;
```

## 인터페이스

> 컬럼/타입 상세 → `Database_Design/docs/DEPENDENCY_MAP.md` Poster_Collection 섹션 참조 (Rule 1).
> 스키마 변경 시 Database_Design 기준으로 이 섹션도 업데이트할 것 (Rule 3).

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.vod` | `full_asset_id`, `series_nm` | VARCHAR(64), VARCHAR | `poster_url IS NULL` 조건으로 수집 대상 조회 |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `public.vod` | `poster_url` | TEXT | VPC 경로 또는 URL |

## 협업 규칙

- `main` 브랜치에 직접 Push 금지 — 반드시 Pull Request
- PR description에 포함 필수:
  1. **변경사항 요약**: 어떤 파일을 추가/수정했는지
  2. **사후영향 평가**: IMPACT_ASSESSOR 에이전트 실행 결과
  3. **보안 점검 보고서**: SECURITY_AUDITOR 에이전트 실행 결과
