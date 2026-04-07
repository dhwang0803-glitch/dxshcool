# 전체 프로젝트 클래스맵

> 최종 수정: 2026-04-01
> 대상: 클래스 기반 전환 완료된 전 브랜치 (`API_Server`, `Hybrid_Layer`, `Vector_Search`, `CF_Engine`, `Poster_Collection`)

---

## 설계 원칙 (공통)

- **Base 클래스 상속**: 각 브랜치별 공통 유틸리티(DB 연결, 설정 로드 등)를 Base에 집중
- **모듈 레벨 싱글턴**: stateless 클래스는 모듈 하단에 인스턴스 1개 생성
- **하위 호환 별칭**: `build_vod_tags = tag_builder.build` 형태로 기존 import 경로 유지 (scripts/ 변경 불필요)
- **순수 함수 = @staticmethod**: 상태 불필요한 연산은 static으로 정의
- **Thread-safety**: mutable 공유 캐시(dict 등)가 있는 클래스는 `threading.Lock`으로 보호

---

## 1. API_Server

> `API_Server/app/services/` — FastAPI 비동기 서비스 레이어

```
BaseService (base_service.py)
│
│   공통 메서드:
│   ├── query(sql, *args) → list[dict]
│   ├── query_one(sql, *args) → dict | None
│   ├── execute(sql, *args) → str
│   ├── acquire() → conn context manager
│   ├── is_test_user(user_id) → bool
│   ├── get_point_balance(user_id, conn=) → int
│   └── deduplicate_series(rows, ...) → list          @staticmethod
│
├── VodService              → get_detail(asset_id)
├── HomeService             → get_banner(), get_sections(), get_personalized_sections(user_id)
├── RecommendService        → get_recommendations(user_id)
├── SimilarService          → get_similar_vods(asset_id, limit)
├── SearchService           → search(query, limit)
├── SeriesService           → get_episodes(), get_progress(), update_progress(), check_purchase(), resolve_vod_id(), get_purchase_options()
├── UserService             → get_watching(), get_history(), get_profile(), get_points(), get_purchases(), get_wishlist()
├── PurchaseService         → create(user_id, series_nm, ...)
├── WishlistService         → add(), remove()
└── NotificationService     → get_list(), get_unread_count(), mark_read(), mark_all_read(), delete(), create_reservation_notification()
```

### 비-BaseService 모듈

| 모듈 | 역할 | 구조 |
|------|------|------|
| `db.py` | asyncpg 커넥션 풀 (max_size=10) | `get_pool()` 함수 |
| `progress_buffer.py` | 시청 진행률 인메모리 버퍼 → 60초 batch flush | `dict` + `asyncio.Lock` |
| `pg_listener.py` | PG LISTEN/NOTIFY → WebSocket push | 콜백 함수 |
| `exceptions.py` | `APIError` 예외 클래스 | 독립 클래스 |

---

## 2. Hybrid_Layer

> `Hybrid_Layer/src/` — 하이브리드 추천 리랭킹 파이프라인

```
HybridBase (base.py)
│
│   공통 메서드:
│   ├── get_conn() → psycopg2.connection               @staticmethod
│   ├── is_test_filter(alias, test_mode) → str          @staticmethod
│   └── batch_upsert(conn, sql_template, rows, ...) → int  @staticmethod
│
├── TagBuilder (tag_builder.py)
│   ├── _calc_confidence(vote_count, vote_avg) → float  @staticmethod
│   ├── parse_cast(raw) → list[str]                     @staticmethod
│   ├── parse_director(raw) → list[str]                 @staticmethod
│   ├── parse_genre_detail(raw) → list[str]             @staticmethod
│   ├── normalize_rating(raw) → str | None              @staticmethod
│   ├── extract_tags_from_row(row) → list[tuple]        @staticmethod
│   └── build(self, conn) → int                         instance
│
├── PreferenceBuilder (preference_builder.py)
│   └── build(self, conn, min_watch_count=2, test_mode=False) → int
│
├── Reranker (reranker.py)
│   ├── _fetch_user_candidates(cur, user_id, ...) → list[dict]   @staticmethod
│   ├── _fetch_user_preferences(cur, user_id) → dict             @staticmethod
│   ├── _fetch_vod_tags(cur, vod_ids) → dict                     @staticmethod
│   ├── _dump_all_candidates(cur, src_table) → dict              @staticmethod
│   ├── _dump_all_preferences(cur) → dict                        @staticmethod
│   ├── score_user(candidates, user_prefs, ...) → list[dict]     @staticmethod
│   ├── rerank_user(self, cur, user_id, ...) → list[dict]        instance
│   └── run(self, conn, ...) → int                               instance
│
└── ShelfBuilder (shelf_builder.py)
    ├── _dump_user_preferences(self, conn, ...) → tuple          instance
    ├── _build_tag_vod_cache(conn, tag_list) → dict              @staticmethod
    ├── _dump_watch_history(self, conn, ...) → dict              instance
    ├── _prepare_cold_start(self, conn, ...) → tuple             instance
    ├── _assemble_shelves(user_ids, ...) → list[tuple]           @staticmethod
    └── build(self, conn, vods_per_tag=10, ...) → int            instance
```

### 싱글턴 & 하위호환 별칭

| 클래스 | 인스턴스 | 주요 별칭 |
|--------|---------|----------|
| TagBuilder | `tag_builder` | `parse_cast`, `build_vod_tags` |
| PreferenceBuilder | `preference_builder` | `build_user_preferences` |
| Reranker | `reranker` | `rerank_user`, `run_hybrid_reranking` |
| ShelfBuilder | `shelf_builder` | `build_tag_shelves` |

### db.py

`get_conn = HybridBase.get_conn` (별칭 전용, 클래스 없음)

---

## 3. Vector_Search

> `Vector_Search/src/` — 벡터 유사도 검색 엔진

```
VectorSearchBase (base.py)
│
│   공통 메서드:
│   ├── get_conn() → connection (pgvector 등록)         @staticmethod
│   └── load_config() → dict                            @staticmethod
│
├── ClipSearcher (clip_based.py)
│   └── search(self, vod_id, conn, top_n=None) → list[dict]     instance
│
├── ContentSearcher (content_based.py)
│   └── search(self, vod_id, conn, top_n=None) → list[dict]     instance
│
├── EnsembleScorer (ensemble.py)
│   └── score(clip_results, content_results, alpha=, top_n=) → list[dict]  @staticmethod
│
└── VisualSimilarity (visual_similarity.py)
    ├── extract_clip_vector(embedding_896d) → ndarray(512,)      @staticmethod
    └── search(self, user_id, conn, top_n=None) → list[dict]     instance
```

### 싱글턴 & 하위호환 별칭

| 클래스 | 인스턴스 | 주요 별칭 |
|--------|---------|----------|
| ClipSearcher | `clip_searcher` | `get_similar_by_clip` |
| ContentSearcher | `content_searcher` | `get_similar_by_meta` |
| EnsembleScorer | `ensemble_scorer` | `ensemble_scores` |
| VisualSimilarity | `visual_similarity` | `get_visual_recommendations` |

### db.py

`get_connection()` — 독립 함수 (scripts/ 상대 import 호환, VectorSearchBase.get_conn 미사용)

---

## 4. CF_Engine

> `CF_Engine/src/` — 협업 필터링 추천 엔진

```
CFBase (base.py)
│
│   공통 메서드:
│   └── get_conn() → psycopg2.connection                @staticmethod
│
├── DataLoader (data_loader.py)
│   └── load_matrix(self, conn, alpha=40, filter_quality=False)
│       → (csr_matrix, user_encoder, item_encoder, user_decoder, item_decoder)
│
├── ALSModel (als_model.py)
│   ├── train(mat, factors=128, iterations=20, ...) → ALS model   @staticmethod
│   └── recommend_all(model, mat, top_k=20, ...) → (user_ids, item_indices, scores)  @staticmethod
│
└── Recommender (recommender.py)
    ├── load_vod_series_map(conn) → dict[str, tuple]             @staticmethod
    └── build_records(user_ids, item_indices, scores, ...) → list[dict]  @staticmethod
```

### 싱글턴 & 하위호환 별칭

| 클래스 | 인스턴스 | 주요 별칭 |
|--------|---------|----------|
| DataLoader | `data_loader` | `load_matrix`, `get_conn` |
| ALSModel | `als_model` | `train`, `recommend_all` |
| Recommender | `recommender` | `load_vod_series_map`, `build_records` |

---

## 5. Poster_Collection

> `Poster_Collection/src/` — 포스터 수집 파이프라인

```
PosterBase (base.py)
│
│   공통 메서드:
│   └── title_similarity(a, b) → float                  @staticmethod
│
├── TMDBPoster (tmdb_poster.py)
│   ├── _tmdb_headers() → dict                          @staticmethod
│   ├── _tmdb_params(extra=None) → dict                 @staticmethod
│   ├── _tmdb_available() → bool                        @staticmethod
│   ├── _item_names(item) → list[str]                   @staticmethod
│   ├── _title_similarity(a, b) → float                 @staticmethod
│   ├── _item_sim(query, item) → float                  @classmethod
│   ├── _search_by_type(series_nm, ct_cl=) → dict|None  @classmethod
│   ├── _get_tv_detail(tmdb_id) → dict|None             @classmethod
│   └── search(series_nm, season=1, ct_cl=, ...) → dict|None  @classmethod
│
├── TvingPoster (tving_poster.py)  ⚠️ threading.Lock 보호
│   ├── parse_season_from_title(title) → (str, int)     @staticmethod
│   ├── parse_season_from_asset_nm(asset_nm) → (str, int)  @staticmethod
│   ├── _fetch_one(p_code) → dict|None                  @staticmethod
│   ├── build_index(index_path=, workers=30, ...) → dict  @classmethod
│   ├── _load_index(index_path=) → dict                 @classmethod  🔒 _index_lock
│   ├── _get_channel(p_code) → str                      @classmethod  🔒 _channel_lock
│   └── search(series_nm, season=1, ...) → dict|None    @classmethod
│
├── ImageDownloader (image_downloader.py)
│   ├── _safe_filename(series_id) → str                 @staticmethod
│   └── download(series_id, image_url, local_dir) → str|None  @staticmethod
│
├── OCIUploader (oci_uploader.py)
│   ├── _get_client() → ObjectStorageClient             @staticmethod
│   ├── build_public_url(region, ns, bucket, name) → str  @staticmethod
│   ├── upload_file(local_path, object_name) → str      @classmethod
│   ├── object_exists(object_name) → bool               @classmethod
│   └── _content_type(suffix) → str                     @staticmethod
│
└── DBUpdater (db_updater.py)
    ├── update_poster_urls(conn, mapping) → int          @staticmethod
    └── update_poster_urls_by_season(conn, season_mapping, parse_fn) → int  @staticmethod
```

### 싱글턴 & 하위호환 별칭

| 클래스 | 인스턴스 | 주요 별칭 |
|--------|---------|----------|
| TMDBPoster | `_tmdb` | `search`, `_tmdb_headers`, `_search_by_type` |
| TvingPoster | `_tving` | `search`, `build_index`, `parse_season_from_asset_nm` |
| ImageDownloader | `_downloader` | `download`, `_safe_filename` |
| OCIUploader | `_uploader` | `build_public_url`, `upload_file`, `object_exists` |
| DBUpdater | `_updater` | `update_poster_urls`, `update_poster_urls_by_season` |

### Thread-safety

| 속성 | Lock | 보호 대상 |
|------|------|----------|
| `TvingPoster._index_cache` | `_index_lock` | JSON 인덱스 최초 로드 (double-checked locking) |
| `TvingPoster._channel_cache` | `_channel_lock` | 채널 캐시 dict 병렬 읽기/쓰기 |

---

## 브랜치 간 의존 관계

```
                    ┌─── CF_Engine ──────┐
                    │                    │
Database_Design ────┼─── Vector_Search ──┼──→ API_Server ──→ Frontend
                    │                    │
                    ├─── Hybrid_Layer ───┘
                    │
                    └─── Poster_Collection (독립)
```

- **API_Server**는 CF_Engine / Vector_Search / Hybrid_Layer의 DB 결과를 읽기 전용으로 사용
- **Poster_Collection**은 다른 추천 브랜치와 독립 (vod.poster_url 쓰기만)
- 모든 브랜치가 `Database_Design`의 스키마를 업스트림으로 참조

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
