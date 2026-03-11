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

- **업스트림**: `Database_Design` 스키마 — vod 테이블
- **다운스트림**: vod 테이블 결측치 채움 → API_Server가 완성된 메타데이터를 서빙
