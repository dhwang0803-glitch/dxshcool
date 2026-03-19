# Cloud Run 파이프라인 배포 계획

> 작성일: 2026-03-19
> 상태: 검토 중 (초안)

---

## 1. 배경

프로젝트 내 자동화 파이프라인이 매일/매주/매월 정기 실행되어야 하나,
로컬 PC 기반 실행은 PC 종료 시 실행 불가. **Google Cloud Run Jobs + Cloud Scheduler** 조합으로 정기 실행을 자동화한다.

### Cloud Run Jobs 선택 이유

| 대안 | 탈락 사유 |
|------|----------|
| Google Colab | 세션 타임아웃, 내장 cron 없음 — 1회성 GPU 작업용 |
| GitHub Actions | 무료 2,000분/월 제한, 메모리 상한 낮음 |
| Oracle VPC 2 | 1 core / 1GB — 연산 부족 |
| **Cloud Run Jobs** | vCPU/메모리 유연 할당, 실행 중에만 과금, 무료 티어 넉넉 |

### Cloud Run Jobs 핵심 스펙

- 리소스: 최대 4 vCPU / 16GB RAM
- 과금: 실행 중에만 (idle 비용 0)
- 무료 티어: 매월 vCPU 360K초 + 메모리 180K GiB초
- 타임아웃: 기본 10분, 최대 24시간
- Cloud Scheduler 연동으로 cron 등록

---

## 2. 전체 브랜치 파이프라인 스캔 결과

2026-03-19 기준, 전 브랜치(11개) 스크립트를 스캔하여 정기 실행 대상과 1회성을 분류함.

### 2.1 정기 실행 대상 (Cloud Run Job 후보)

| # | 브랜치 | 스크립트 | 용도 | 주기 | 리소스 | DB | 비고 |
|---|--------|---------|------|------|--------|-----|------|
| 1 | Database_Design | `db_maintenance.py` | MV 3개 REFRESH CONCURRENTLY + 파티션 자동 생성 (2주 선행) | 매일 자정 | 중량 | R/W | 운영 필수, DEFAULT 파티션 이상 감지 포함 |
| 2 | Shopping_Ad | `crawl_products.py` | 홈쇼핑 6채널 EPG 크롤링 → `homeshopping_product` UPSERT | 매일 자정 | 중량 | W | Playwright 브라우저 자동화, 6채널 병렬 |
| 3 | CF_Engine | `train.py` | ALS 행렬분해 학습 → `serving.vod_recommendation` 적재 | 주 1회 | 중량 | R/W | 242K 유저 × 166K VOD, alpha=40, factors=128 |
| 4 | CF_Engine | `full_eval.py` | NDCG/MRR/HitRate 종합 평가 리포트 생성 | 주 1회 | 중량 | R | train.py 직후 순차 실행 |
| 5 | Normal_Recommendation | `run_pipeline.py` | 장르별(영화/드라마/예능/애니) 인기 Top-20 → `serving.popular_recommendation` | 주 1회 | 경량 | R/W | TTL 7일, rating 60% + 최신성 40% |
| 6 | Vector_Search | `run_pipeline.py` → `export_to_db.py` | 벡터 유사도 앙상블(CLIP 0.4 + Meta 0.6) → `serving.vod_recommendation` | 주 1회 | 경량 | R/W | 로컬 parquet 기반 numpy 연산, ~42분 |
| 7 | User_Embedding | `run_embed.py` | 시청이력 기반 user_embedding 896차원 재계산 → DB 적재 | 주 1회 | 중량 | R/W | 225K 유저, weighted_mean, batch UPSERT |
| 8 | Database_Design | `fill_tmdb_ratings.py` | TMDB 평점 미수집 VOD 일괄 수집 (ThreadPoolExecutor 20 workers) | 월 1회 | 중량 | R/W | 현재 커버리지 74.4%, 신규 VOD 추가 시 |
| 9 | Database_Design | `genre_classify_full.py` | TV 연예/오락 세부장르 LLM 분류 (Few-shot) | 월 1회 | 중량 | R/W | Ollama exaone3.5 필요 — Cloud Run 부적합 |
| 10 | RAG | `run_bulk_meta.py` | TMDB→KMDB→JW→DATA_GO 4단계 메타데이터 수집 | 월 1회 | 중량 | R/W | 시리즈 dedup으로 API 호출 10배 절감 |
| 11 | VOD_Embedding | `batch_embed.py` | CLIP ViT-B/32 512차원 영상 임베딩 | 월 1회 | 중량 | 없음 | GPU 권장 — Cloud Run 부적합 |
| 12 | Poster_Collection | `run_full_pipeline.py` | 포스터 크롤링 → OCI 업로드 → DB poster_url 반영 | 월 1회 | 중량 | R/W | 4분할 병렬 크롤링, Naver API |

### 2.2 1회성 스크립트 (Cloud Run 불필요)

| 브랜치 | 스크립트 | 용도 |
|--------|---------|------|
| Database_Design | `migrate.py` | 초기 CSV → PostgreSQL 데이터 적재 (user, vod, watch_history) |
| Database_Design | `validate_data.py` | 마이그레이션 전 CSV 사전 검증 (중복, FK, 범위) |
| Database_Design | `pilot_db_test.py` | VPC PostgreSQL 접속 및 pgvector 진단 |
| Database_Design | `vod_ingest_pipeline.py` | 신규 VOD 트레일러 CLIP 임베딩 + DB INSERT (온디맨드) |
| Database_Design | `pilot_genre_classify.py` | 세부장르 분류 파일럿 100건 (아카이브) |
| Database_Design | `pilot_genre_fewshot.py` | Few-shot 파일럿 (아카이브) |
| Database_Design | `filter_web_content.py` | 웹드라마/웹예능 필터링 (TMDB networks 기반) |
| Database_Design | `fill_cast_guest_from_naver.py` | Naver 검색 기반 cast_guest 보완 |
| Database_Design | `fill_cast_guest_from_tmdb.py` | TMDB credits 기반 cast_guest 보완 |
| Database_Design | `ingest_new_vods_from_tmdb.py` | TMDB_NEW_2025 VOD 일괄 적재 |
| CF_Engine | `pilot_test.py` | ALS 학습 속도 측정 + poster_url 커버리지 (5K 샘플) |
| CF_Engine | `inspect_recommendations.py` | 추천 결과 육안 검증 (시청이력 vs 추천 비교) |
| CF_Engine | `score_cutoff_analysis.py` | 점수 급락 지점 분석 (최적 K 결정) |
| CF_Engine | `pilot_cutoff_visual.py` | 점수 감쇠 시각화 (10유저 bar chart) |
| CF_Engine | `export_to_db.py` | CF 추천 결과 DB 적재 (train.py가 호출) |
| Vector_Search | `dump_embeddings.py` | DB 벡터 → 로컬 parquet 1회 다운로드 |
| Vector_Search | `search.py` | 단건 VOD 유사 콘텐츠 검색 (개발/테스트용) |
| Vector_Search | `evaluate_precision.py` | Genre Precision@k 품질 검증 |
| Normal_Recommendation | `export_to_db.py` | parquet → DB 적재 (조장 전용) |
| Object_Detection | `batch_detect.py` | YOLOv11s 배치 객체 탐지 → parquet (로컬/GPU) |
| Object_Detection | `batch_clip_score.py` | CLIP zero-shot 장면 태깅 → parquet |
| Object_Detection | `batch_stt_score.py` | Whisper STT 키워드 추출 → parquet |
| Object_Detection | `prepare_local_dataset.py` | AI Hub 음식 데이터 YOLO 전처리 |
| Object_Detection | `analyze_pilot.py` | 파일럿 카테고리별 인식률 통계 |
| RAG | `run_cast_guest.py` | cast_guest 결측치 채우기 (TMDB credits + Ollama) |
| RAG | `run_naver_meta.py` | Naver 검색 기반 메타데이터 수집 (비동기 병렬) |
| VOD_Embedding | `crawl_trailers.py` | YouTube 트레일러 다운로드 (체크포인트 지원) |
| VOD_Embedding | `ingest_to_db.py` | 영상 임베딩 pkl → pgvector 적재 |
| Poster_Collection | `crawl_posters.py` | Naver 포스터 수집 (4분할 병렬) |
| Poster_Collection | `export_manifest.py` | manifest CSV 생성 |
| Poster_Collection | `upload_to_oci.py` | OCI Object Storage 업로드 |

---

## 3. Cloud Run Job 구성안 (초안)

정기 실행 12개 중 Cloud Run 적합한 것만 **주기별 3개 Job**으로 묶는다.

### 3.1 Job 구성

| Cloud Run Job | 주기 | Cron (KST) | 포함 스크립트 | 순서 | 리소스 | 예상 실행시간 |
|---------------|------|------------|-------------|------|--------|-------------|
| `daily-maintenance` | 매일 | 00:00 | `db_maintenance.py` → `crawl_products.py` | 순차 | 2 vCPU / 4GB | ~10분 |
| `weekly-recommend` | 매주 일 | 02:00 | `run_embed.py` → `train.py` → `full_eval.py` → VS `run_pipeline.py` → VS `export_to_db.py` → NR `run_pipeline.py` | 순차 | 2 vCPU / 8GB | ~1시간 |
| `monthly-ingest` | 매월 1일 | 03:00 | `fill_tmdb_ratings.py` → `run_bulk_meta.py` → `run_full_pipeline.py` (Poster) | 순차 | 2 vCPU / 4GB | ~2시간 |

### 3.2 Cloud Run 부적합 (로컬/Colab 유지)

| 스크립트 | 사유 | 대안 |
|---------|------|------|
| `genre_classify_full.py` | Ollama LLM 서버 필요 | 로컬 실행 (월 1회 수동) |
| `batch_embed.py` | GPU(CLIP ViT-B/32) 권장 | Colab 또는 로컬 GPU |
| Object_Detection 전체 | GPU(YOLO/CLIP/Whisper) + 대용량 영상 | Colab 또는 로컬 GPU |

### 3.3 실행 순서 의존성

```
[매일 00:00] daily-maintenance
  db_maintenance.py         ← MV REFRESH + 파티션 생성
  crawl_products.py         ← 홈쇼핑 EPG 수집

[매주 일 02:00] weekly-recommend
  User_Embedding/run_embed.py       ← 사용자 벡터 재계산 (선행 필수)
  CF_Engine/train.py                ← ALS 학습 + 추천 적재
  CF_Engine/full_eval.py            ← 평가 리포트
  Vector_Search/run_pipeline.py     ← 벡터 유사도 계산
  Vector_Search/export_to_db.py     ← 결과 DB 적재
  Normal_Recommendation/run_pipeline.py  ← 인기 추천 갱신

[매월 1일 03:00] monthly-ingest
  fill_tmdb_ratings.py              ← 신규 VOD TMDB 평점
  run_bulk_meta.py                  ← 메타데이터 수집
  run_full_pipeline.py              ← 포스터 수집 + 업로드
```

### 3.4 비용 예상 (무료 티어 내)

| Job | vCPU 소비 (월) | 메모리 소비 (월) | 무료 한도 |
|-----|--------------|----------------|----------|
| daily-maintenance | 30일 × 600초 × 2 = 36,000초 | 30일 × 600초 × 4GiB = 72,000 GiB초 | |
| weekly-recommend | 4주 × 3,600초 × 2 = 28,800초 | 4주 × 3,600초 × 8GiB = 115,200 GiB초 | |
| monthly-ingest | 1회 × 7,200초 × 2 = 14,400초 | 1회 × 7,200초 × 4GiB = 28,800 GiB초 | |
| **합계** | **79,200초** | **216,000 GiB초** | vCPU 360K초 / 메모리 180K GiB초 |

> 메모리가 무료 한도(180K)를 약간 초과할 수 있음 — weekly-recommend의 메모리를 4GB로 낮추거나, 실행시간 단축으로 조정 가능.

---

## 4. 인프라 요구사항

### 4.1 컨테이너 이미지

```dockerfile
# Dockerfile (예시)
FROM python:3.12-slim
RUN apt-get update && apt-get install -y libpq-dev
# Playwright (Shopping_Ad용)
RUN pip install playwright && playwright install chromium --with-deps
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . /app
WORKDIR /app
```

### 4.2 Secret Manager

| Secret 이름 | 용도 | 사용 Job |
|-------------|------|---------|
| `db-host` | PostgreSQL 호스트 | 전체 |
| `db-port` | PostgreSQL 포트 | 전체 |
| `db-name` | 데이터베이스명 | 전체 |
| `db-user` | DB 사용자명 | 전체 |
| `db-password` | DB 비밀번호 | 전체 |
| `tmdb-api-key` | TMDB API 키 | monthly-ingest |
| `naver-client-id` | Naver API ID | monthly-ingest |
| `naver-client-secret` | Naver API Secret | monthly-ingest |

### 4.3 네트워크

- Oracle VPC PostgreSQL이 public IP인 경우: Cloud Run에서 직접 접속 가능
- IP 화이트리스트에 Cloud Run 이그레스 IP 추가 필요
- 리전: `asia-northeast3` (서울) 권장 — DB 레이턴시 최소화

---

## 5. 미결 사항

- [ ] Cloud Run Job별 Dockerfile 분리 vs 단일 이미지
- [ ] weekly-recommend 메모리 최적화 (무료 한도 초과 가능성)
- [ ] Shopping_Ad Phase 2 완성 후 daily Job에 매칭 로직 추가
- [ ] entrypoint.sh 분기 방식 vs 개별 Job 생성 방식
- [ ] CI/CD 연동 (코드 push 시 자동 이미지 빌드)
- [ ] 로깅/알림 체계 (Cloud Logging → Slack 알림)
- [ ] Oracle VPC 방화벽 규칙 설정 (Cloud Run IP 허용)
- [ ] genre_classify_full.py Ollama를 Cloud Run에서 실행 가능한지 검토
- [ ] batch_embed.py GPU 대안 (Cloud Run GPU 지원 여부)
