# VOD_Embedding 세션 보고서 — 2026-03-12 오후

## 작업 요약

### 1. PostgreSQL 재설치 후 DB 접속 확인
- 재설치 완료, `.env` 접속 정보 재확인 → 정상 접속 확인

### 2. batch_embed.py 버그 수정 — YouTube ID 중복 이슈

**원인**: `crawl_trailers.py`의 yt-dlp `outtmpl`이 `%(id)s.%(ext)s` (YouTube ID 기반 파일명)이므로, 여러 `vod_id`가 동일 YouTube 영상을 가리킬 경우 같은 파일명으로 저장됨. `--delete-after-embed` 시 첫 번째 vod_id 처리 후 파일 삭제 → 나머지 vod_id들 임베딩 실패.

**수정 내용** (`scripts/batch_embed.py`):
- `filename` 기준으로 vod_id 그룹핑 (`defaultdict(list)`)
- 파일 1회 임베딩 → 그룹 내 모든 vod_id에 동일 벡터 복사 (vod_id마다 독립 행)
- 파일 삭제는 그룹 전체 처리 완료 후 1회

**결과**:
- 293 vod_id / 169 고유 파일 처리 → 124건이 벡터 공유로 구제됨
- 신규 성공 +288건, 신규 실패 +5건 (partial file — 다운로드 불완전)

### 3. Parquet 저장

| 항목 | 값 |
|------|---|
| 파일명 | `data/embeddings_신정윤.parquet` |
| 행 수 | 5,026건 |
| 임베딩 차원 | 512 (CLIP ViT-B/32) |
| 파일 크기 | 10.3 MB |

---

## 현재 파이프라인 상태 (2026-03-12 13:17 기준)

### STEP 1. 트레일러 크롤링

| 항목 | 값 |
|------|---|
| 대상 | 11,508건 (tasks_C.json) |
| 처리완료 | 5,580건 (48.5%) |
| 성공 | 5,382건 (96.5%) |
| 실패 | 198건 |
| 디스크 잔여 | 62.9 MB (22개 파일) |
| 마지막 갱신 | 2026-03-12T12:42:15 |

- **잔여**: 5,928건 미크롤링 → 재시작 필요

### STEP 2. CLIP 임베딩

| 항목 | 값 |
|------|---|
| 성공 | 5,026건 |
| 실패 | 4,799건 |
| 저장 배치 | 311개 |

- 실패 원인: ① 이전 YouTube ID 중복 버그(수정 완료), ② partial file(다운로드 불완전)
- 잔여 22개 파일은 크롤링 재시작 후 다음 임베딩 실행 시 처리

### STEP 3. Parquet

- `data/embeddings_신정윤.parquet` 생성 완료 (5,026건, 10.3MB)
- 크롤링 완료 후 추가 임베딩 → parquet 재생성 예정

---

## 다음 세션 작업

1. 크롤링 재시작 (체크포인트에서 이어서): `scripts/crawl_trailers.py --task-file data/tasks_C.json --trailers-dir data/trailers`
2. 크롤링 완료 후 임베딩 재실행: `scripts/batch_embed.py --trailers-dir data/trailers --output pkl --delete-after-embed`
3. 최종 parquet 재생성 (전체 결과 통합): `embeddings_신정윤.parquet` 갱신
