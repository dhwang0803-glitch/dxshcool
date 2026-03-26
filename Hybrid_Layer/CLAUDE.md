# Hybrid_Layer — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

---

## 모듈 역할

**설명 가능한 추천(Explainable Recommendation) 생성**

CF_Engine과 Vector_Search가 각각 생산한 추천 후보(top 20씩)를 입력으로 받아,
`vod_tag` × `user_preference` 기반으로 리랭킹하고 **추천 근거(explanation_tags)**를 생성한다.

> "봉준호 감독 작품을 즐겨 보셨어요" — 이런 설명을 프론트엔드에 표시하기 위한 레이어.

### 데이터 플로우

```
━━━ 입력 (기존 엔진 산출물) ━━━━━━━━━━━━━━━━━━━━━━━━━━

  serving.vod_recommendation
    ├── CF_Engine:     user_id → COLLABORATIVE 타입
    │     3배수 후보 추출 → ct_cl 기준 시리즈 중복제거 → 저장
    └── Vector_Search: source_vod_id → CONTENT_BASED 타입 (user_id=NULL)
          3배수 후보 추출 → ct_cl 기준 시리즈 중복제거 → 저장

  ※ Vector_Search는 콘텐츠 유사도 기반 (user_id 없음)
     → Phase 3 reranker의 유저별 후보 조회에 포함되지 않음
     → CF(COLLABORATIVE) 후보만 Phase 3에 입력

━━━ Phase 1: VOD 태그 추출 (1회성, 갱신 시) ━━━━━━━━━━

  public.vod (director, cast_lead, genre 등)
    → build_vod_tags.py
    → public.vod_tag (~100만건 예상)

━━━ Phase 2: 유저 선호 프로필 집계 (주기적) ━━━━━━━━━━

  public.watch_history × public.vod_tag
    → build_user_preferences.py
    → public.user_preference (유저 × 태그 affinity)

━━━ Phase 3: 리랭킹 + 설명 생성 (주기적) ━━━━━━━━━━━━

  serving.vod_recommendation (CF 후보, 시리즈 중복제거 완료 상태)
    → vod_id 기준 중복 제거
    → 후보 × vod_tag × user_preference 매칭
    → hybrid_score = β × original_score + (1-β) × tag_overlap_score
    → 상위 10건 + explanation_tags 생성
    → serving.hybrid_recommendation 적재

  ※ 시리즈 중복제거를 Phase 3에서 추가하지 않는다.
     CF_Engine이 이미 시리즈 중복제거 후 저장하므로 이중 적용 시
     top_n 미달 위험이 있다.

━━━ Phase 4: 선호 태그별 VOD 선반 생성 (주기적) ━━━━━

  user_preference → 유저별 top 5 태그
    → 태그별 vod_tag 매칭 + 시청 제외 + 시리즈 중복제거 + 랭킹
    → 태그별 top 10 VOD 선별
    → serving.tag_recommendation 적재

  ※ Phase 4는 vod_tag에서 직접 후보를 뽑으므로 CF/Vector 중복제거와
     무관하게 자체적으로 시리즈 중복제거를 수행해야 한다. (아래 규칙 참조)

━━━ 서빙 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  홈 배너 3단 구조:
    1단: Normal_Recommendation → serving.personalized_banner (유저별 top 5)
    2단: Normal_Recommendation → serving.popular_recommendation (비개인화 top 5)
    3단: Hybrid_Layer → serving.hybrid_recommendation (top 10)

  API_Server: GET /home/banner (JWT user_id)
    → 1단 personalized_banner + 2단 popular + 3단 hybrid 조합
    → 비로그인 시 2단만 표시

  API_Server: GET /recommend/{user_id}
    → serving.hybrid_recommendation + serving.tag_recommendation 조회
    → top_vod + patterns(태그별 그룹핑) + explanation_tags 반환
```

---

## 파일 위치 규칙 (MANDATORY)

```
Hybrid_Layer/
├── src/          ← import 전용 라이브러리 (직접 실행 X)
├── scripts/      ← 직접 실행 스크립트
├── tests/        ← pytest
├── config/       ← yaml 설정
└── docs/
    └── plans/    ← PLAN 설계 문서
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| VOD 태그 추출 로직 | `src/tag_builder.py` |
| 유저 선호 집계 로직 | `src/preference_builder.py` |
| 리랭킹 + 설명 생성 | `src/reranker.py` |
| VOD 태그 적재 스크립트 | `scripts/build_vod_tags.py` |
| 유저 선호 집계 스크립트 | `scripts/build_user_preferences.py` |
| 리랭킹 + serving 적재 | `scripts/run_hybrid.py` |
| pytest | `tests/` |
| 리랭킹 설정 (β, top_n 등) | `config/hybrid_config.yaml` |

**`Hybrid_Layer/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

---

## 기술 스택

```python
import psycopg2              # DB 조회 + 적재
import json                  # explanation_tags JSONB 직렬화
from dotenv import load_dotenv
import yaml                  # 설정 파일
```

```bash
conda activate myenv
pip install psycopg2-binary pyyaml python-dotenv
```

---

## 테이블 소유

| 테이블 | 위치 | 설명 |
|--------|------|------|
| `public.vod_tag` | **VPC** | VOD 해석 가능 태그 (DDL은 Database_Design, 초기 적재는 이 브랜치) |
| `public.user_preference` | **VPC** | 유저별 태그 선호 프로필 (이 브랜치가 생산) |
| `serving.hybrid_recommendation` | **VPC** | 최종 설명 가능 추천 (이 브랜치가 생산, API_Server가 소비) |
| `serving.tag_recommendation` | **VPC** | 카테고리별 태그 선반 — genre 3 + genre_detail 3 + director 2 + actor 4 × VOD 10 |

---

## 인터페이스

> 컬럼/타입 상세 → `Database_Design/docs/DEPENDENCY_MAP.md` 참조 (Rule 1).
> 스키마 변경 시 Database_Design 기준으로 이 섹션도 업데이트 (Rule 3).

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `serving.vod_recommendation` | `user_id_fk`, `vod_id_fk`, `score`, `recommendation_type` | VARCHAR/VARCHAR/REAL/VARCHAR | CF 후보 조회 (COLLABORATIVE, user_id_fk IS NOT NULL) |
| `public.vod` | `full_asset_id`, `director`, `cast_lead`, `cast_guest`, `genre`, `genre_detail`, `ct_cl`, `series_nm` | - | vod_tag 생성 소스 + 시리즈 중복제거용 |
| `public.watch_history` | `user_id_fk`, `vod_id_fk`, `completion_rate` | VARCHAR/VARCHAR/REAL | user_preference 집계 |
| `public.vod_tag` | `vod_id_fk`, `tag_category`, `tag_value`, `confidence` | VARCHAR/VARCHAR/VARCHAR/REAL | 리랭킹 매칭 |
| `public.user_preference` | `user_id_fk`, `tag_category`, `tag_value`, `affinity` | VARCHAR/VARCHAR/VARCHAR/REAL | 리랭킹 매칭 |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `public.vod_tag` | `vod_id_fk`, `tag_category`, `tag_value`, `confidence` | VARCHAR/VARCHAR/VARCHAR/REAL | ON CONFLICT DO NOTHING |
| `public.user_preference` | `user_id_fk`, `tag_category`, `tag_value`, `affinity`, `watch_count`, `avg_completion` | - | ON CONFLICT UPSERT |
| `serving.hybrid_recommendation` | `user_id_fk`, `vod_id_fk`, `rank`, `score`, `explanation_tags`, `source_engines` | - | ON CONFLICT UPSERT |
| `serving.tag_recommendation` | `user_id_fk`, `tag_category`, `tag_value`, `tag_rank`, `tag_affinity`, `vod_id_fk`, `vod_rank`, `vod_score` | - | 선호 태그 선반 |

---

## 리랭킹 스코어 공식

```python
# 1. 후보 수집: CF 후보 (COLLABORATIVE, 시리즈 중복제거 완료) → vod_id 기준 중복 제거
# 2. 태그 매칭: 후보 VOD의 vod_tag × 유저의 user_preference
# 3. 스코어:

tag_overlap_score = mean(top 3 matched tag affinities)  # 상위 3개 매칭 태그

hybrid_score = β × original_score + (1 - β) × tag_overlap_score
# β: 원본 엔진 스코어 가중치 (config, 기본 0.6)

# 4. hybrid_score 기준 상위 10건 선별
# 5. explanation_tags = 매칭된 태그 목록 (affinity 내림차순)
```

---

## ⚠️ 시리즈 중복제거 규칙 (MANDATORY)

### Phase 3 (reranker.py) — 시리즈 중복제거 하지 않는다

CF_Engine이 `serving.vod_recommendation`에 저장할 때 이미 시리즈 중복제거를 완료한다.
reranker에서 추가로 중복제거하면 후보가 과도하게 줄어 top_n=10 미달 위험이 있다.
reranker는 **hybrid_score 기준 재정렬만** 수행한다.

### Phase 4 (shelf_builder.py) — 시리즈 중복제거 필수

`vod_tag`에서 직접 후보를 조회하므로 CF/Vector의 중복제거와 무관하다.
아래 기준으로 시리즈 중복제거를 적용한다.

#### vod_tag tag_category 허용값 (DB 제약 기준)

`'director', 'actor_lead', 'actor_guest', 'genre', 'genre_detail'`

- `actor_lead`: `cast_lead`(주연) 에서 추출
- `actor_guest`: `cast_guest`(게스트/조연) 에서 추출
- (마이그레이션: `20260324_actor_tag_split.sql` — 기존 `actor` 단일값에서 분리)

#### 에피소드 단위 유지 조건 (중복제거 제외)

```python
is_episode_level = (tag_category in ("actor_guest", "director") and ct_cl == "TV 연예/오락")
```

**적용 이유:**
특정 배우나 감독이 홍보 등 목적으로 여러 TV 연예/오락 프로그램에 게스트(cast_guest)로
출연한 경우, 해당 인물의 팬인 유저에게 "영화배우A가 출연한 예능 몰아보기" 형태의
배너를 제공하기 위해 에피소드 단위 추천을 유지한다.

예시 배너 문구: *"영화배우A가 출연한 TV 연예/오락 시리즈 몰아보기 어떠신가요?"*

- `actor_lead`(주연)는 에피소드 단위 **제외** → 시리즈 중복제거 적용
  - 이유: 예능 레귤러 출연자의 에피소드 10개가 배너를 독점하는 것 방지

#### 시리즈 단위 중복제거 (그 외 모든 경우)

- TV 연예/오락이라도 `tag_category`가 `actor_guest`/`director`가 아니면 시리즈 중복제거
  - 이유: 같은 예능의 에피소드 10개가 하나의 배너를 독점하면 광고 공간 낭비
- 드라마, 영화, 다큐 등 모든 장르 — 시리즈당 1건만

```python
# shelf_builder.py 구현 기준
if not is_episode_level:
    if series_nm in seen_series:
        continue
    seen_series.add(series_nm)
```

### API_Server와의 역할 분리

| 처리 위치 | 역할 |
|-----------|------|
| `shelf_builder.py` (Phase 4) | 카테고리별 슬롯 할당 + 시리즈 중복제거 + 10개 미달 스킵 후 tag_recommendation 적재 |
| `API_Server/home_service.py` | genre 태그 배너 + 벡터 유사도 + TOP10 조회 |
| `API_Server/recommend_service.py` | genre_detail + actor + director 태그 배너 + 벡터 유사도 조회 |

**10개 미달 태그 스킵**: shelf_builder가 태그별 VOD를 필터링한 후 10개 미만이면
해당 태그를 스킵하고 같은 카테고리의 후순위 태그(affinity 차순위)로 자동 대체한다.

---

## 배너 구조 (홈 / 스마트 추천)

### 홈 페이지 — 10개 배너

| # | 배너 | 소스 | 개인화 |
|---|------|------|--------|
| 1~4 | 추천 인기 {CT_CL} (영화/TV드라마/애니메이션/TV 연예·오락) | `serving.popular_recommendation` | X (글로벌) |
| 5~7 | 추천 인기 {genre} (유저 선호 장르 top 3) | `serving.tag_recommendation` (genre) | O |
| 8~9 | 나의 취향과 비슷한 {장르} (벡터 유사도 top 2 그룹) | `user_embedding` meta 384D <=> `vod_meta_embedding` | O |
| 10 | {유저}님만을 위한 추천 시리즈 TOP10 | `tag_recommendation` score 상위 + `serving.rec_sentence` | O |

### 스마트 추천 페이지

| 구간 | 배너 | 소스 |
|------|------|------|
| 히어로 | top_vod (hybrid 최상위, poster_url 우선) | `serving.hybrid_recommendation` |
| 태그 배너 | genre_detail 3 + director 2 + actor_lead 2 + actor_guest 2 (affinity 상위, 자연 경쟁) | `serving.tag_recommendation` |
| 벡터 배너 | 나의 취향과 비슷한 콘텐츠 (벡터 유사도 top 10) | `user_embedding` meta 384D <=> `vod_meta_embedding` |

### shelf_builder 카테고리별 슬롯

| 카테고리 | 슬롯 수 | 소비 페이지 |
|----------|---------|------------|
| `genre` | 3 | 홈 |
| `genre_detail` | 3 | 스마트 추천 |
| `director` | 2 | 스마트 추천 |
| `actor_lead` | 2 | 스마트 추천 |
| `actor_guest` | 2 | 스마트 추천 |
| ~~`rating`~~ | **제거** | — |

---

## 구현 단계

| Phase | 작업 | 스크립트 | 의존성 |
|-------|------|---------|--------|
| **1** | vod → vod_tag 태그 추출 적재 | `scripts/build_vod_tags.py` | `public.vod` 메타데이터 |
| **2** | watch_history × vod_tag → user_preference 집계 | `scripts/build_user_preferences.py` | Phase 1 + `watch_history` |
| **3** | CF+Vector 후보 리랭킹 → hybrid_recommendation 적재 | `scripts/run_hybrid.py` | Phase 2 + `serving.vod_recommendation` |
| **4** | 카테고리별 슬롯 × VOD top 10 선반 생성 (10개 미달 스킵) | `scripts/build_tag_shelves.py` | Phase 2 |

---

## ⚠️ 인프라 제약

- VPC: 1 core / 1GB RAM (+3GB swap) / 150GB Storage → **thin serving layer**
- Phase 1~2 집계 연산은 **로컬 머신**에서 수행 가능 (SQL로 VPC 직접 집계도 가능)
- VPC에는 최종 결과(`vod_tag`, `user_preference`, `hybrid_recommendation`)만 적재

---

## 협업 규칙

- `main` 브랜치 직접 Push 금지 — 반드시 PR
- CF_Engine / Vector_Search의 `serving.vod_recommendation` 스키마 변경 시 이 파일 업데이트
- `serving.hybrid_recommendation` 스키마 확정 완료 — 구현 가능
