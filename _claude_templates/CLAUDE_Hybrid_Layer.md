# Hybrid_Layer — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

**설명 가능한 추천(Explainable Recommendation) 생성**

CF_Engine + Vector_Search 추천 후보(각 top 20)를 `vod_tag` × `user_preference`로 리랭킹하고
추천 근거(`explanation_tags`)를 생성하여 `serving.hybrid_recommendation`에 적재한다.

> "봉준호 감독 작품을 즐겨 보셨어요" — 프론트엔드 표시용 설명 생성.

## 파일 위치 규칙 (MANDATORY)

```
Hybrid_Layer/
├── src/       ← import 전용 라이브러리 (직접 실행 X)
├── scripts/   ← 직접 실행 스크립트 (python scripts/xxx.py)
├── tests/     ← pytest
├── config/    ← yaml 설정
└── docs/      ← 설계 문서
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| VOD 태그 추출 | `src/tag_builder.py` |
| 유저 선호 집계 | `src/preference_builder.py` |
| 리랭킹 + 설명 생성 | `src/reranker.py` |
| VOD 태그 적재 스크립트 | `scripts/build_vod_tags.py` |
| 유저 선호 집계 스크립트 | `scripts/build_user_preferences.py` |
| 리랭킹 + serving 적재 | `scripts/run_hybrid.py` |
| pytest | `tests/` |
| 리랭킹 설정 | `config/hybrid_config.yaml` |

## 기술 스택

```python
import psycopg2              # DB 조회 + 적재
import json                  # JSONB 직렬화
from dotenv import load_dotenv
import yaml                  # 설정
```

## 테이블 소유

| 테이블 | 위치 | 설명 |
|--------|------|------|
| `public.vod_tag` | VPC | VOD 해석 가능 태그 |
| `public.user_preference` | VPC | 유저별 태그 선호 프로필 |
| `serving.hybrid_recommendation` | VPC | 최종 설명 가능 추천 |

## 인터페이스

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `serving.vod_recommendation` | `user_id_fk`, `vod_id_fk`, `score`, `recommendation_type` | VARCHAR/VARCHAR/REAL/VARCHAR | CF + Vector 후보 |
| `public.vod` | `director`, `cast_lead`, `cast_guest`, `genre`, `genre_detail`, `rating` | - | vod_tag 소스 |
| `public.watch_history` | `user_id_fk`, `vod_id_fk`, `completion_rate` | - | user_preference 집계 |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `public.vod_tag` | `vod_id_fk`, `tag_category`, `tag_value` | VARCHAR/VARCHAR/VARCHAR | DO NOTHING |
| `public.user_preference` | `user_id_fk`, `tag_category`, `tag_value`, `affinity`, `watch_count`, `avg_completion` | - | UPSERT |
| `serving.hybrid_recommendation` | `user_id_fk`, `vod_id_fk`, `rank`, `score`, `explanation_tags`, `source_engines` | - | UPSERT |

## ⚠️ 인프라 제약

- VPC: 1 core / 1GB RAM → thin serving layer
- 집계 연산은 로컬에서 수행
- VPC에는 최종 결과만 적재
