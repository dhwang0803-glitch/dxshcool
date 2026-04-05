# VOD Recommendation System — 기술 스택

> 프로젝트 전체 브랜치 순회 기반 기술 스택 종합 (2026-04-05 기준)

---

## 1. Language & Runtime

| 기술 | 버전 | 사용 브랜치 |
|------|------|------------|
| Python | 3.12 | 전 브랜치 |
| SQL (PostgreSQL) | - | Database_Design, API_Server |
| Conda | myenv | 전 브랜치 |

---

## 2. Web Framework (Backend)

| 기술 | 용도 | 사용 브랜치 |
|------|------|------------|
| FastAPI | REST API 백엔드 서버 | API_Server |
| Uvicorn | ASGI 서버 | API_Server |
| Pydantic v2 | 요청/응답 스키마 검증 | API_Server |
| CORS Middleware | 프론트엔드 CORS 허용 | API_Server |

---

## 3. Database & Storage

| 기술 | 용도 | 사용 브랜치 |
|------|------|------------|
| PostgreSQL | 메인 RDBMS | 전 브랜치 |
| pgvector | 벡터 유사도 검색 (IVF_FLAT) | Database_Design, VOD_Embedding, Vector_Search, CF_Engine |
| pg_trgm | 퍼지/초성 문자열 검색 | Database_Design, API_Server |
| asyncpg | 비동기 PostgreSQL 드라이버 | API_Server |
| psycopg2 | 동기 PostgreSQL 드라이버 | 배치 파이프라인 전반 |
| OCI Object Storage | 포스터 이미지 CDN | Poster_Collection |
| Apache Parquet (pyarrow) | 중간 데이터 교환 포맷 | VOD_Embedding, Object_Detection, gen_rec_sentence |
| Materialized View | 사전 집계 캐시 (Gold Layer) | Database_Design |
| PostgreSQL LISTEN/NOTIFY | 실시간 유저 활동 알림 | API_Server |

---

## 4. ML/AI & Data Science

| 기술 | 용도 | 사용 브랜치 |
|------|------|------------|
| PyTorch | 딥러닝 프레임워크 | VOD_Embedding, Object_Detection |
| OpenAI CLIP (ViT-B/32) | 영상 프레임 임베딩 (512차원) | VOD_Embedding |
| sentence-transformers | 텍스트/이미지 임베딩 (paraphrase-multilingual-MiniLM-L12-v2, clip-ViT-B-32-multilingual-v1) | VOD_Embedding, Object_Detection |
| implicit (ALS) | 행렬분해 협업필터링 | CF_Engine |
| scikit-learn | MiniBatchKMeans 클러스터링, PCA 차원축소 | gen_rec_sentence |
| Ultralytics YOLOv11 | 객체 탐지 (한식 71종 커스텀 모델) | Object_Detection |
| OpenAI Whisper | 한국어 음성인식 (STT) | Object_Detection |
| EasyOCR | 자막 OCR 텍스트 추출 (한국어/영어) | Object_Detection |
| OpenCV | 프레임 추출, 이미지 처리 | VOD_Embedding, Object_Detection |
| Pillow (PIL) | 이미지 변환, GIF 생성 | VOD_Embedding, Object_Detection, Shopping_Ad |
| Ollama | 로컬 LLM 추론 (gemma3:27b-it-qat) | gen_rec_sentence, RAG |
| vLLM | 비동기 LLM 서빙 (Colab A100) | gen_rec_sentence |
| Google Gemma 2/3 | 추천 문구 생성 LLM (27B 최종) | gen_rec_sentence |
| EXAONE 3.5 (LG AI Research) | RAG 메타데이터 폴백 LLM | RAG |
| NumPy | 수치 연산 | 거의 전 브랜치 |
| pandas | 데이터프레임 처리 | CF_Engine, Object_Detection, gen_rec_sentence 등 |
| SciPy | 희소 행렬 (csr_matrix) | CF_Engine |

---

## 5. Cloud & Infrastructure

| 기술 | 용도 | 사용 브랜치 |
|------|------|------------|
| Google Cloud Run | API 서버 배포 (vod-api-dev / vod-api) | API_Server |
| Oracle Cloud Infrastructure (OCI) | Object Storage (포스터 CDN) | Poster_Collection |
| Google Colab (A100 GPU) | 대규모 LLM 배치 추론 | gen_rec_sentence |
| Docker | 컨테이너 빌드 (python:3.12-slim) | API_Server |

---

## 6. APIs & External Services

| 서비스 | 용도 | 사용 브랜치 |
|--------|------|------------|
| TMDB (The Movie Database) | 영화/TV 메타데이터, 포스터, 평점 | RAG, Poster_Collection |
| KMDB (한국영상자료원) | 한국 콘텐츠 메타데이터 (TMDB 폴백) | RAG |
| JustWatch | 스트리밍 정보 (폴백) | RAG |
| 공공데이터포털 (DATA_GO) | 공공 콘텐츠 데이터 (최종 폴백) | RAG |
| Naver | 메타데이터 수집 (cast_lead 등) | RAG |
| Tving | 포스터 이미지 크롤링 | Poster_Collection |
| YouTube (yt-dlp) | 트레일러 영상 수집 | VOD_Embedding |
| 제철장터 (LG HelloVision) | 홈쇼핑 편성표 크롤링 | Shopping_Ad |
| 지역 축제 API | 지자체 축제 정보 조회 | Shopping_Ad |

---

## 7. 크롤링 & 스크래핑

| 기술 | 용도 | 사용 브랜치 |
|------|------|------------|
| Playwright | 브라우저 자동화 (비동기), GIF 캡처 | Shopping_Ad |
| requests | HTTP API 호출 | RAG, Poster_Collection, Shopping_Ad |
| BeautifulSoup4 | HTML 파싱 | RAG |
| curl-cffi | 비동기 스크래핑 | RAG |
| yt-dlp | YouTube 트레일러 다운로드 | VOD_Embedding |
| ffmpeg | 영상 → 오디오 추출 (16kHz WAV) | Object_Detection |

---

## 8. 인증 & 보안

| 기술 | 용도 | 사용 브랜치 |
|------|------|------------|
| python-jose (JWT HS256) | JWT 토큰 발급/검증 | API_Server |
| HTTPBearer (FastAPI) | Bearer 토큰 인증 미들웨어 | API_Server |
| python-dotenv | .env 환경변수 관리 | 전 브랜치 |

---

## 9. Testing & DevOps

| 기술 | 용도 | 사용 브랜치 |
|------|------|------------|
| pytest | 단위/통합 테스트 | 전 브랜치 |
| pytest-asyncio | 비동기 테스트 | API_Server |
| httpx (AsyncClient) | FastAPI 비동기 테스트 클라이언트 | API_Server |
| GitHub | 소스 코드 관리, PR 워크플로우 | 전 브랜치 |
| GitHub CLI (gh) | PR 생성/관리 자동화 | main |
| Docker / Dockerfile | 컨테이너 이미지 빌드 | API_Server |

---

## 10. 기타

| 기술 | 용도 | 사용 브랜치 |
|------|------|------------|
| PyYAML | 설정 파일 파싱 | Object_Detection, Shopping_Ad, API_Server, Hybrid_Layer 등 |
| tqdm | 진행 표시바 | 전 브랜치 |
| aiohttp | 비동기 HTTP (vLLM 호출) | gen_rec_sentence |
| asyncio | 비동기 프로그래밍 | API_Server, gen_rec_sentence, Shopping_Ad |
| concurrent.futures | 멀티스레드 병렬 처리 | RAG, Poster_Collection |

---

## 브랜치별 핵심 기술 요약

| 브랜치 | 핵심 기술 |
|--------|----------|
| **main** | Python 3.12, Conda, GitHub, Docker |
| **API_Server** | FastAPI, asyncpg, JWT, Cloud Run, Docker |
| **CF_Engine** | implicit (ALS), SciPy sparse matrix |
| **Database_Design** | PostgreSQL DDL, pgvector, pg_trgm, Materialized Views |
| **Hybrid_Layer** | CF + Vector 리랭킹 로직 |
| **Normal_Recommendation** | pandas 인기도 기반 추천 |
| **Object_Detection** | YOLOv11, Whisper STT, EasyOCR, CLIP, OpenCV, ffmpeg |
| **Poster_Collection** | TMDB/Tving 크롤링, OCI Object Storage |
| **RAG** | TMDB/KMDB/Naver/JustWatch API, Ollama (EXAONE 3.5) |
| **Shopping_Ad** | Playwright, Pillow (GIF 생성), 제철장터/축제 API |
| **User_Embedding** | NumPy 벡터 연산, pgvector |
| **VOD_Embedding** | CLIP ViT-B/32, yt-dlp, OpenCV, PyTorch |
| **Vector_Search** | pgvector cosine similarity |
| **gen_rec_sentence** | Ollama (Gemma3 27B), vLLM, KMeans, Colab A100 |
