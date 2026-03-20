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
    ├── CF_Engine:     user_id → top 20 (COLLABORATIVE)
    └── Vector_Search: user_id → top 20 (VISUAL_SIMILARITY)

━━━ Phase 1: VOD 태그 추출 (1회성, 갱신 시) ━━━━━━━━━━

  public.vod (director, cast_lead, genre 등)
    → build_vod_tags.py
    → public.vod_tag (~100만건 예상)

━━━ Phase 2: 유저 선호 프로필 집계 (주기적) ━━━━━━━━━━

  public.watch_history × public.vod_tag
    → build_user_preferences.py
    → public.user_preference (유저 × 태그 affinity)

━━━ Phase 3: 리랭킹 + 설명 생성 (주기적) ━━━━━━━━━━━━

  serving.vod_recommendation (CF 20 + Vector 20)
    → 중복 제거 (최대 40 → 유니크 후보)
    → 후보 × vod_tag × user_preference 매칭
    → hybrid_score = β × vector_score + (1-β) × tag_overlap_score
    → 상위 20건 + explanation_tags 생성
    → serving.hybrid_recommendation 적재

━━━ Phase 4: 선호 태그별 VOD 선반 생성 (주기적) ━━━━━

  user_preference → 유저별 top 5 태그
    → 태그별 vod_tag 매칭 + 시청 제외 + 랭킹
    → 태그별 top 10 VOD 선별
    → serving.tag_recommendation 적재

━━━ 서빙 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  API_Server: GET /recommendations/{user_id}
    → serving.hybrid_recommendation 조회
    → explanation_tags와 함께 프론트엔드에 반환

  API_Server: GET /recommendations/{user_id}/tags
    → serving.tag_recommendation 조회
    → 선호 태그 5개 × VOD 10개 선반 데이터 반환
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
| `serving.tag_recommendation` | **VPC** | 선호 태그별 VOD 추천 선반 — top 5 태그 × top 10 VOD |

---

## 인터페이스

> 컬럼/타입 상세 → `Database_Design/docs/DEPENDENCY_MAP.md` 참조 (Rule 1).
> 스키마 변경 시 Database_Design 기준으로 이 섹션도 업데이트 (Rule 3).

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `serving.vod_recommendation` | `user_id_fk`, `vod_id_fk`, `score`, `recommendation_type` | VARCHAR/VARCHAR/REAL/VARCHAR | CF + Vector 후보 조회 |
| `public.vod` | `full_asset_id`, `director`, `cast_lead`, `cast_guest`, `genre`, `genre_detail`, `rating` | - | vod_tag 생성 소스 |
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
# 1. 후보 수집: CF 20건 + Vector 20건 → 중복 제거
# 2. 태그 매칭: 후보 VOD의 vod_tag × 유저의 user_preference
# 3. 스코어:

tag_overlap_score = mean(top 3 matched tag affinities)  # 상위 3개 매칭 태그

hybrid_score = β × original_score + (1 - β) × tag_overlap_score
# β: 원본 엔진 스코어 가중치 (config, 기본 0.6)

# 4. hybrid_score 기준 상위 20건 선별
# 5. explanation_tags = 매칭된 태그 목록 (affinity 내림차순)
```

---

## 구현 단계

| Phase | 작업 | 스크립트 | 의존성 |
|-------|------|---------|--------|
| **1** | vod → vod_tag 태그 추출 적재 | `scripts/build_vod_tags.py` | `public.vod` 메타데이터 |
| **2** | watch_history × vod_tag → user_preference 집계 | `scripts/build_user_preferences.py` | Phase 1 + `watch_history` |
| **3** | CF+Vector 후보 리랭킹 → hybrid_recommendation 적재 | `scripts/run_hybrid.py` | Phase 2 + `serving.vod_recommendation` |
| **4** | 선호 태그 top 5 × VOD top 10 선반 생성 | `scripts/build_tag_shelves.py` | Phase 2 |

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
