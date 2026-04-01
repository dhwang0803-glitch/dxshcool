# gen_rec_sentence — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

LLM(Ollama) 기반으로 VOD별 감성 카피(`rec_sentence`)를 생성하여 `serving.rec_sentence` 테이블에 적재하는 파이프라인.
홈 TOP10 배너 포스터 하단에 노출되며, 유저 세그먼트(K-Means k=5)별로 톤을 분화한다.

## 파이프라인 개요

```
[context_builder.py]  DB → VOD 메타 + CLIP 512d 임베딩 조합
        ↓
[visual_extractor.py] CLIP text probing → 시각 키워드 5개 추출 (선택)
        ↓
[sentence_generator.py] Ollama gemma3:27b-it-qat → rec_sentence JSON
        ↓
[quality_filter.py]   길이(20~80자) / 금칙어 / 클리셰 / 제목반복 검증
        ↓
[batch_generate.py]   세그먼트별 배치 생성 (5 seg × ~65K VOD)
        ↓
[ingest_results.py]   results.parquet → serving.rec_sentence UPSERT
```

## 코드 위치 (IMPORTANT)

이 브랜치에는 **소스 코드가 커밋되어 있지 않다.**
코드는 로컬 작업 디렉터리와 Colab 노트북에서 운영된다.

| 파일 | 위치 | 역할 |
|------|------|------|
| `context_builder.py` | 로컬 | DB → VOD 메타 + 임베딩 + 층화 추출 |
| `visual_extractor.py` | 로컬 | CLIP text probing 29개 시각 묘사어 |
| `sentence_generator.py` | 로컬 | Ollama 추론 + JSON 응답 파싱 |
| `quality_filter.py` | 로컬 | 다단계 품질 검증 (길이/금칙어/클리셰/HTML/느낌표) |
| `batch_generate.py` | 로컬/Colab | 프로덕션 배치 (--offline 모드, resume, 자동저장) |
| `fill_seed_sentences.py` | 로컬 | Seed 데이터 배치 생성 |
| `build_seed_data.py` | 로컬 | --stratify 층화 추출 seed 구성 |
| `cluster_users.py` | 로컬 | PCA 50d + MiniBatchKMeans k=5 유저 세그먼트 |
| `export_for_colab.py` | 로컬 | 추천 풀 VOD 메타 parquet 추출 (오프라인용) |
| `ingest_results.py` | 로컬 | Colab results.parquet → DB UPSERT (500건 배치) |
| `colab_batch_generate.ipynb` | Colab | A100 GPU 오프라인 배치 노트북 |

## 모델 선정 이력

| 모델 | 상태 | 사유 |
|------|------|------|
| gemma2:9b | 탈락 | 장면 시각화 우수하나 Minimal 프롬프트에서 패턴 모방 |
| gemma3:12b-it-qat | 탈락 | 길이 지시 일관 무시, 규칙 과부하 → 할루시네이션 |
| **gemma3:27b-it-qat** | **채택** | 복합 지시 안정 처리, A100 VRAM 충분 (17GB/40GB) |

## 유저 세그먼트 (K-Means k=5)

| seg | 레이블 | 특성 |
|-----|--------|------|
| 0 | 키즈/애니 집중층 | 애니·키즈 편중 |
| 1 | 예능/오락 집중층 | TV 연예/오락 위주 |
| 2 | 드라마 집중형 | 드라마 중심 (콜드스타트 기본값) |
| 3 | 가족 시청층 | 드라마+애니 혼합 (부모+자녀) |
| 4 | 영화 탐색층 | 영화 중심 |

## 인터페이스

> 컬럼/타입 상세 → `Database_Design/docs/DEPENDENCY_MAP.md` gen_rec_sentence 섹션 참조 (Rule 1).

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.vod` | `full_asset_id`, `asset_nm`, `ct_cl` | VARCHAR | 대상 VOD 식별 |
| `public.vod` | `genre`, `genre_detail`, `director` | VARCHAR | LLM 입력 메타데이터 |
| `public.vod` | `cast_lead`, `smry`, `rating` | TEXT/VARCHAR | LLM 입력 메타데이터 |
| `public.vod` | `poster_url` | TEXT | 포스터 존재 여부 필터 |
| `public.vod_embedding` | `vod_id_fk`, `embedding` | VARCHAR/VECTOR(512) | CLIP 영상 벡터 → visual_extractor 입력 |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `serving.rec_sentence` | `user_id_fk` | VARCHAR(64) | FK → user.sha2_hash, UNIQUE(user_id_fk, vod_id_fk) |
| `serving.rec_sentence` | `vod_id_fk` | VARCHAR(64) | FK → vod.full_asset_id |
| `serving.rec_sentence` | `rec_reason` | TEXT | TOP10 선정 이유 (포스터 우측 상단) |
| `serving.rec_sentence` | `rec_sentence` | TEXT | 감성 카피 (포스터 하단, 20~80자) |
| `serving.rec_sentence` | `generated_at` | TIMESTAMPTZ | 생성 시각 |
| `serving.rec_sentence` | `expires_at` | TIMESTAMPTZ | TTL 7일 |

## 문서

| 파일 | 내용 |
|------|------|
| `docs/EXPLORATION_LOG.md` | 전체 탐색 과정 기록 (18개 섹션, 모델 선정·품질 필터·세그먼트 설계·Colab 배치) |

## Colab 오프라인 배치 워크플로우

```
로컬: export_for_colab.py → vod_contexts.parquet (13K VOD)
  ↓ Google Drive 업로드
Colab: batch_generate.py --offline → results.parquet
  ↓ Google Drive 다운로드
로컬: ingest_results.py → serving.rec_sentence UPSERT (500건 배치)
```

VPC 방화벽으로 Colab→DB 직접 접속 불가 → parquet 기반 오프라인 워크플로우 채택.

---

**마지막 수정**: 2026-04-01
**프로젝트 상태**: Colab 프로덕션 배치 실행 중 (gemma3:27b-it-qat, ~65K x 5 seg)
