# RAG — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

외부 API(TMDB → KMDB → JustWatch → Naver → 영상물등급위원회)를 통해
VOD 테이블의 결측치(director, cast_lead, cast_guest, rating, release_date, smry)를 자동으로 채운다.

## 파일 위치 규칙 (MANDATORY)

```
RAG/
├── src/       ← import 전용 라이브러리 (직접 실행 X)
├── scripts/   ← 직접 실행 파이프라인 (python scripts/run_xxx.py)
├── tests/     ← pytest
├── config/    ← rag_config.yaml, api_keys.env.example
└── docs/      ← 파일럿 결과 리포트, 설계 문서
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| API 연동 함수, 파싱 로직 | `src/` |
| 유효성 검증 함수 | `src/validation.py` |
| 실행 파이프라인 (`run_*.py`) | `scripts/` |
| pytest | `tests/` |
| `.yaml`, `.env.example` | `config/` |

**`RAG/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
import requests           # API 호출
from curl_cffi.requests import AsyncSession  # 비동기 스크래핑
import psycopg2           # DB 연결
from dotenv import load_dotenv
from tqdm import tqdm     # 진행률
from concurrent.futures import ThreadPoolExecutor  # 병렬 처리
```

## 소스 폴백 순서

```
TMDB → KMDB → JustWatch (GraphQL) → Naver → DATA_GO(영상물등급위원회)
```

## import 규칙

```python
# scripts/ 에서 src/ 모듈 import 방법
ROOT = Path(__file__).resolve().parents[2]  # scripts/는 parents[2]가 ROOT
_SRC = ROOT / "RAG" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
import meta_sources as rab
from validation import validate_cast
```

## 인터페이스

> 컬럼/타입 상세 → `Database_Design/docs/DEPENDENCY_MAP.md` RAG 섹션 참조 (Rule 1).
> 스키마 변경 시 Database_Design 기준으로 이 섹션도 업데이트할 것 (Rule 3).

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.vod` | `full_asset_id` | VARCHAR(64) | 처리 대상 식별 |
| `public.vod` | `asset_nm`, `genre`, `ct_cl` | VARCHAR | RAG 검색 쿼리 생성 |
| `public.vod` | `rag_processed` | BOOLEAN | FALSE인 레코드만 처리 |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `public.vod` | `director` | VARCHAR(255) | |
| `public.vod` | `cast_lead`, `cast_guest` | TEXT | |
| `public.vod` | `rating` | VARCHAR(16) | |
| `public.vod` | `release_date` | DATE | |
| `public.vod` | `smry` | TEXT | |
| `public.vod` | `rag_processed` | BOOLEAN | 완료 시 TRUE |
| `public.vod` | `rag_source` | VARCHAR(64) | TMDB/KMDB/JW 등 |
| `public.vod` | `rag_processed_at` | TIMESTAMPTZ | |
| `public.vod` | `rag_confidence` | REAL | 0.0~1.0 |
