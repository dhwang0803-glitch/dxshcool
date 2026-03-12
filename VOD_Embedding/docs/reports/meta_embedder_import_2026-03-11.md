# 메타데이터 임베딩 코드 이식 보고서

- **작성일**: 2026-03-11
- **출처**: `billionaireahreum/lg2-ahreum` — `user_embedding/pipeline/`
- **대상 경로**: `VOD_Embedding/src/`

---

## 이식된 파일 목록

| 원본 파일 | 이식 경로 | 역할 |
|-----------|-----------|------|
| `config.py` | `src/config.py` | 임베딩 파이프라인 설정 (모델명, DB 연결, 배치 크기) |
| `db.py` | `src/db.py` | psycopg2 연결 컨텍스트 매니저, dict 변환 헬퍼 |
| `generate_embeddings.py` | `src/meta_embedder.py` | VOD 메타데이터 임베딩 생성 파이프라인 (run() 함수 진입점) |

> `generate_embeddings.py` → `meta_embedder.py` 로 이름 변경:
> CLAUDE.md 컨벤션상 `src/`는 import 전용 모듈이므로 역할을 명확히 표현하는 이름으로 변경.
> 실행은 추후 `scripts/run_meta_embed.py` 에서 `from src.meta_embedder import run` 형태로 호출.

---

## 각 파일 상세

### `src/config.py`
- `python-dotenv`로 `.env` 자동 로드
- DB 접속 정보 환경변수 참조 (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`)
- 임베딩 모델: `paraphrase-multilingual-MiniLM-L12-v2` (384차원, 한국어 지원, 무료)
- 배치 크기: 256 (메모리에 따라 조정 가능)

### `src/db.py`
- `get_conn()`: 트랜잭션 단위 psycopg2 연결 컨텍스트 매니저 (commit/rollback 자동 처리)
- `fetch_all_as_dict()`: 커서 결과를 `list[dict]`로 변환
- DB 비밀번호 미설정 시 `getpass`로 터미널 입력 요청

### `src/meta_embedder.py`
- **핵심 로직**: 시리즈 단위 그룹핑 → 대표 텍스트 선택 → 배치 인코딩 → DB 저장
- `normalize_title()`: 에피소드 번호, 화질 태그 등 제거 후 시리즈 그룹핑 키로 사용
- `build_vod_text()`: 제목/유형/장르/감독/주연/조연/줄거리/개봉연도 → 임베딩 입력 텍스트
- `pick_representative()`: 시리즈 내 메타데이터 완성도 높은 row를 대표로 선택
- `run()`: 전체 파이프라인 실행 (모델 로드 → VOD 조회 → 그룹핑 → 인코딩 → DB 저장)
- `print_summary()`: 임베딩 완료 현황 출력
- 멱등성 보장: `ON CONFLICT (vod_id_fk, embedding_type) DO UPDATE`

---

## 이식 시 변경사항

### 보안 수정 (필수)
| 항목 | 원본 | 수정 후 |
|------|------|---------|
| `DB_NAME` 기본값 | `os.getenv("DB_NAME", "vod_recommendation")` | `os.getenv("DB_NAME")` |
| `DB_USER` 기본값 | `os.getenv("DB_USER", "postgres")` | `os.getenv("DB_USER")` |
| `DB_HOST` 기본값 | `os.getenv("DB_HOST", "localhost")` | `os.getenv("DB_HOST")` |

> 루트 `CLAUDE.md` 보안 규칙: `os.getenv()` 기본값에 실제 인프라 정보 금지.

---

## 알려진 이슈 (실행 전 해결 필요)

### 🔴 `is_active` 컬럼 미존재
`fetch_all_vods()`에서 `WHERE is_active = TRUE` 조건을 사용하나,
현재 `vod` 테이블에 해당 컬럼이 없음.

**해결 방법**: `Database_Design` 브랜치에서 마이그레이션 선행
```sql
ALTER TABLE vod ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;
```

---

## 다음 작업

- [ ] `scripts/run_meta_embed.py` 작성 (meta_embedder.run() 호출 스크립트)
- [ ] `Database_Design` 브랜치에 `vod.is_active` 컬럼 추가 마이그레이션 요청
- [ ] 영상 임베딩 파이프라인 (`src/embedder.py`) 개발
- [ ] 두 임베딩 타입이 `vod_embedding` 테이블에 함께 적재되는지 통합 테스트
