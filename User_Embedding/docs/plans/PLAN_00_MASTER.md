# PLAN_00: User_Embedding 마스터 플랜

**브랜치**: User_Embedding
**작성일**: 2026-03-11
**목표**: 유저의 시청 이력 기반으로 896차원 유저 임베딩 벡터 생성 → `user_embedding` 테이블 적재

> **범위 주의**: 이 브랜치는 유저 벡터 생성까지만 담당한다.
> VOD 벡터와의 ALS 행렬 분해는 `CF_Engine` 브랜치에서 처리한다.

---

## 전체 파이프라인

```
[PLAN_01] DB watch_history 로드
          user_id / asset_id / completion_rate

[PLAN_02] VOD 결합 임베딩 조회
          vod_embedding (CLIP 512) + vod_meta_embedding (METADATA 384)
          → concat → VOD 결합 벡터 [896차원]
          (각 벡터는 VOD_Embedding 브랜치에서 DB 저장 시 정규화 완료된 상태로 가정)

[PLAN_03] 유저 임베딩 생성
          각 유저별 시청 VOD 결합벡터를 completion_rate로 가중 평균
          → L2 정규화 → user_vector [896차원]

[PLAN_04] DB 적재
          user_embedding 테이블 upsert (VECTOR(896))
```

---

## 단계별 요약

| 단계 | 파일 | 입력 | 출력 |
|------|------|------|------|
| PLAN_01 | `src/data_loader.py` | DB `watch_history` | `{user_id_fk: [(asset_id, completion_rate), ...]}` |
| PLAN_02 | `src/vod_embedding_loader.py` | DB `vod_embedding`(CLIP) + `vod_meta_embedding`(METADATA) | `{asset_id: np.ndarray(896,)}` |
| PLAN_03 | `src/user_embedder.py` | user 시청목록 + VOD 벡터 | `{user_id_fk: np.ndarray(896,)}` |
| PLAN_04 | `scripts/run_embed.py` | user 벡터 dict | `user_embedding` 테이블 (컬럼: `user_id_fk`) |

---

## 사전 조건

| 조건 | 확인 방법 |
|------|-----------|
| `vod_embedding` 테이블에 CLIP(512) 적재 완료 | `SELECT COUNT(*) FROM vod_embedding;` |
| `vod_meta_embedding` 테이블에 METADATA(384) 적재 완료 | `SELECT COUNT(*) FROM vod_meta_embedding;` |
| `watch_history` 테이블 존재 | `SELECT COUNT(*) FROM watch_history;` |
| `user_embedding` 테이블 스키마 생성 완료 | `Database_Design` 브랜치 `migrations/20260311_add_meta_user_embedding_tables.sql` 선행 필요 |

---

## 파일 구조

```
User_Embedding/
├── src/
│   ├── db.py                     ← DB 연결 헬퍼
│   ├── data_loader.py            ← PLAN_01: watch_history 로드
│   ├── vod_embedding_loader.py   ← PLAN_02: VOD 결합 임베딩 로드
│   └── user_embedder.py          ← PLAN_03: 유저 벡터 계산
├── scripts/
│   └── run_embed.py              ← PLAN_03+04: 실행 진입점 + DB 적재
├── tests/
│   ├── test_data_loader.py
│   ├── test_vod_loader.py
│   └── test_user_embedder.py
├── config/
│   └── embed_config.yaml
└── docs/
    └── plans/
        ├── PLAN_00_MASTER.md     ← 이 파일
        ├── PLAN_01_DATA_LOADER.md
        ├── PLAN_02_VOD_LOADER.md
        ├── PLAN_03_USER_EMBEDDER.md
        └── PLAN_04_DB_EXPORT.md
```

---

## 실행 명령

```bash
conda activate myenv

# 전체 실행
python scripts/run_embed.py

# 파이럿: 100명 유저만
python scripts/run_embed.py --pilot 100

# 특정 유저 재계산
python scripts/run_embed.py --user-id <user_id>

# DB 적재 결과 검증
python scripts/run_embed.py --verify
```

---

## 설계 결정

### 가중 평균 방식 채택
- 각 유저의 user_vector = `sum(completion_rate_i * vod_vector_i) / sum(completion_rate_i)`
- ALS 없이도 VOD 벡터 공간에서 유저 취향을 즉시 표현 가능
- CF_Engine(ALS)에서 이 벡터를 초기값으로 활용하여 개인화 고도화

### 최소 시청 조건
- 결합 임베딩(CLIP + METADATA 모두 존재)이 있는 VOD 시청 이력이 **1건 이상**인 유저만 생성
- 조건 미충족 유저는 건너뛰고 로그 기록

### 멱등성
- 동일 user_id 재실행 시 기존 벡터 덮어쓰기 (`ON CONFLICT ... DO UPDATE`)
- `updated_at` 컬럼으로 마지막 갱신 시각 추적

### 차원
- VOD 결합 임베딩과 동일한 **896차원** 유지
- CF_Engine이 동일 공간에서 유저-아이템 유사도 계산 가능

---

## 진행 체크리스트

- [ ] PLAN_01: `src/data_loader.py` — watch_history 로드
- [ ] PLAN_02: `src/vod_embedding_loader.py` — VOD 결합 임베딩 구성
- [ ] PLAN_03: `src/user_embedder.py` — 가중 평균 유저 벡터 생성
- [ ] PLAN_04: `scripts/run_embed.py` — DB 적재 + 검증
- [ ] `config/embed_config.yaml` 작성
- [ ] pytest 작성 및 통과
- [ ] 파이럿 100명 결과 `docs/reports/` 저장

---

**다음**: PLAN_01_DATA_LOADER.md
