# Phase 1: 핵심 스키마 DDL 작성 계획

**단계**: Phase 1 / 5
**목표**: USER, VOD, WATCH_HISTORY 3개 핵심 테이블의 PostgreSQL DDL 작성
**산출물**: `schema/create_tables.sql`, `schema/create_indexes.sql`, `schema/DESIGN.md`

---

## 1. 작업 순서

```
1. USER 테이블 DDL 작성
2. VOD 테이블 DDL 작성
3. WATCH_HISTORY 테이블 DDL 작성 (FK 의존: USER, VOD)
4. 인덱스 생성 스크립트 작성
5. 트리거 작성 (updated_at 자동 갱신, 만족도 계산)
6. 제약조건 확인
7. DESIGN.md 작성
```

---

## 2. USER 테이블 설계

### 컬럼 정의

| 컬럼명 | 타입 | 제약 | 원본 컬럼 | 비고 |
|--------|------|------|----------|------|
| sha2_hash | VARCHAR(64) | PK | sha2_hash | SHA2 해시된 사용자 ID |
| age_grp10 | VARCHAR(16) | NOT NULL | AGE_GRP10 | 10대~90대이상 (9개 값) |
| inhome_rate | REAL | | INHOME_RATE | 집내 시청 비율 0~100 |
| svod_scrb_cnt_grp | VARCHAR(16) | | SVOD_SCRB_CNT_GRP | "0건", "1건" 등 |
| paid_chnl_cnt_grp | VARCHAR(16) | | PAID_CHNL_CNT_GRP | "0건", "1건" 등 |
| ch_hh_avg_month1 | REAL | | CH_HH_AVG_MONTH1 | 월 평균 TV 시청 시간 |
| kids_use_pv_month1 | REAL | | KIDS_USE_PV_MONTH1 | 키즈 콘텐츠 월 이용 |
| nfx_use_yn | BOOLEAN | | NFX_USE_YN | Netflix 사용 여부 |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | - | 레코드 생성 시간 |
| last_active_at | TIMESTAMPTZ | DEFAULT NOW() | - | 마지막 활동 시간 |

### 정규화 검증
- **1NF**: 모든 속성이 원자값 (svod_scrb_cnt_grp은 VARCHAR로 "0건" 등 원자값)
- **2NF**: 단일 PK (sha2_hash) → 부분 종속 없음
- **3NF**: 모든 비키 컬럼이 PK에만 종속 → 이행 종속 없음

### 원본 데이터 변환 참고
```
AGE_GRP10: "60대", "50대" 등 한국어 값 → 그대로 저장
SVOD_SCRB_CNT_GRP: "0건", "1건" → 그대로 저장 (INTEGER 변환 고려 가능)
NFX_USE_YN: "Y"/"N" → TRUE/FALSE 변환
INHOME_RATE: 0.0~100.0 실수값
```

---

## 3. VOD 테이블 설계

### 컬럼 정의

| 컬럼명 | 타입 | 제약 | 원본 컬럼 | NULL 허용 이유 |
|--------|------|------|----------|--------------|
| full_asset_id | VARCHAR(64) | PK | full_asset_id | |
| asset_nm | VARCHAR(255) | NOT NULL | asset_nm | |
| ct_cl | VARCHAR(32) | NOT NULL | CT_CL | 영화/라이프 등 대분류 |
| disp_rtm | VARCHAR(8) | | disp_rtm | "HH:MM" 형식 원본 |
| disp_rtm_sec | INTEGER | NOT NULL | disp_rtm_sec | 초 단위 변환값 |
| genre | VARCHAR(64) | | genre | |
| director | VARCHAR(255) | NULL | director | RAG 처리 예정, 313건 NULL |
| asset_prod | VARCHAR(64) | | asset_prod | 제작사/배급사 |
| smry | TEXT | NULL | smry | RAG 처리 예정, 28건 NULL |
| provider | VARCHAR(128) | | provider | |
| genre_detail | VARCHAR(255) | | genre_detail | |
| series_nm | VARCHAR(255) | | series_nm | NULL 가능 |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | - | |
| updated_at | TIMESTAMPTZ | DEFAULT NOW() | - | 트리거로 갱신 |
| rag_processed | BOOLEAN | DEFAULT FALSE | - | RAG 처리 완료 여부 |
| rag_source | VARCHAR(64) | NULL | - | IMDB/Wiki/KMRB 등 |
| rag_processed_at | TIMESTAMPTZ | NULL | - | RAG 처리 시각 |

### 정규화 검증
- **1NF**: 원자값 보장 (genre_detail, series_nm 모두 단일 값)
- **2NF**: 단일 PK (full_asset_id) → 부분 종속 없음
- **3NF**: series_nm이 있는 경우 series 테이블 분리 검토
  - **결정**: 현 단계에서는 series_nm을 VOD에 직접 저장 (166,159개 VOD에서 series 별도 관리 시 복잡성 증가)
  - **이유**: series_nm → ct_cl 등의 이행 종속이 존재할 수 있으나, 추천 시스템의 조회 단위가 VOD이므로 비정규화 허용

### RAG 처리 대상 컬럼
```
director: 313건 NULL (0.19%) → IMDB/Wiki에서 검색
smry: 28건 NULL (0.017%) → IMDB/Wiki에서 검색
```

---

## 4. WATCH_HISTORY 테이블 설계

### 컬럼 정의

| 컬럼명 | 타입 | 제약 | 원본 컬럼 | 비고 |
|--------|------|------|----------|------|
| watch_history_id | BIGINT | PK GENERATED ALWAYS AS IDENTITY | - | 자동 생성 |
| user_id_fk | VARCHAR(64) | FK → user.sha2_hash NOT NULL | sha2_hash | |
| vod_id_fk | VARCHAR(64) | FK → vod.full_asset_id NOT NULL | full_asset_id | |
| strt_dt | TIMESTAMPTZ | NOT NULL | strt_dt | 시청 시작 시각 |
| use_tms | REAL | NOT NULL | use_tms | 시청 시간 (초) |
| completion_rate | REAL | | completion_rate | 원본값 그대로 저장 |
| satisfaction | REAL | | satisfaction | 베이지안 스코어 원본값 |
| created_at | TIMESTAMPTZ | DEFAULT NOW() | - | 레코드 삽입 시간 |

### completion_rate 처리 방식
원본 데이터에 이미 completion_rate가 계산되어 있으므로 **원본값 직접 저장**.
PostgreSQL의 GENERATED ALWAYS AS는 단순 수식만 지원하므로, 서브쿼리 방식의 자동 계산은 불가 → 마이그레이션 시 Python에서 계산 후 삽입.

### 만족도(satisfaction) 처리 방식
원본 데이터에 이미 베이지안 스코어 기반 satisfaction이 계산되어 있으므로 **원본값 직접 저장**.
향후 신규 데이터 삽입 시에는 트리거 또는 애플리케이션 레이어에서 계산.

### 제약조건
```sql
-- 복합 유니크: 동일 사용자가 동일 VOD를 같은 시각에 2번 기록 방지
UNIQUE (user_id_fk, vod_id_fk, strt_dt)

-- CHECK 제약
CHECK (use_tms >= 0)
CHECK (completion_rate >= 0 AND completion_rate <= 1)
CHECK (satisfaction >= 0 AND satisfaction <= 1)
```

### 정규화 검증
- **1NF**: 원자값 보장
- **2NF**: 복합 PK 없음 (watch_history_id 단일 PK) → 부분 종속 없음
- **3NF**: completion_rate는 use_tms/disp_rtm으로 계산 가능하나, 성능을 위해 저장된 값 사용 (반정규화 허용)

---

## 5. 인덱스 설계

### WATCH_HISTORY 인덱스 (HIGH 우선순위)

| 인덱스명 | 컬럼 | 타입 | 목적 |
|---------|------|------|------|
| idx_wh_user_id | user_id_fk | BTREE | 사용자별 시청이력 조회 |
| idx_wh_vod_id | vod_id_fk | BTREE | VOD별 시청 통계 조회 |
| idx_wh_strt_dt | strt_dt | BTREE | 날짜 범위 조회 |
| idx_wh_satisfaction | satisfaction | BTREE | 만족도 순위 조회 |
| idx_wh_user_strt | (user_id_fk, strt_dt) | BTREE | 사용자별 시간순 조회 |

### VOD 인덱스 (MEDIUM 우선순위)

| 인덱스명 | 컬럼 | 타입 | 목적 |
|---------|------|------|------|
| idx_vod_ct_cl | ct_cl | BTREE | 콘텐츠 타입 필터링 |
| idx_vod_genre | genre | BTREE | 장르 필터링 |
| idx_vod_provider | provider | BTREE | 제공사 필터링 |
| idx_vod_smry_gin | smry | GIN (to_tsvector) | 텍스트 검색 (FULLTEXT 대체) |

### USER 인덱스 (LOW 우선순위)

| 인덱스명 | 컬럼 | 타입 | 목적 |
|---------|------|------|------|
| idx_user_age_grp | age_grp10 | BTREE | 연령대별 필터링 |
| idx_user_nfx | nfx_use_yn | BTREE | NFX 사용 여부 필터링 |

---

## 6. 트리거 설계 (PostgreSQL)

### updated_at 자동 갱신 트리거 (VOD 테이블)

```sql
-- 트리거 함수 (재사용 가능)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- VOD 테이블에 적용
CREATE TRIGGER trg_vod_updated_at
    BEFORE UPDATE ON vod
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

---

## 7. 파일 작성 계획

### schema/create_tables.sql 구조
```sql
-- 1. 확장 모듈 (필요 시)
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- 퍼지 검색용

-- 2. USER 테이블
CREATE TABLE "user" (...);

-- 3. VOD 테이블
CREATE TABLE vod (...);

-- 4. WATCH_HISTORY 테이블
CREATE TABLE watch_history (...);

-- 5. 트리거 함수
CREATE OR REPLACE FUNCTION update_updated_at_column() ...

-- 6. 트리거 적용
CREATE TRIGGER ...

-- 7. 코멘트 (COMMENT ON TABLE/COLUMN)
```

### schema/create_indexes.sql 구조
```sql
-- WATCH_HISTORY 인덱스 (성능 최우선)
CREATE INDEX idx_wh_user_id ON watch_history (user_id_fk);
...

-- VOD 인덱스
CREATE INDEX idx_vod_ct_cl ON vod (ct_cl);
...

-- USER 인덱스
CREATE INDEX idx_user_age_grp ON "user" (age_grp10);
...
```

---

## 8. 주의사항

1. **user는 PostgreSQL 예약어**: `"user"` 또는 `users`로 테이블명 지정 필요
   - 권장: `"user"` (원본 명칭 유지, 따옴표 사용)
2. **completion_rate 범위**: 원본 데이터에서 1.0을 초과하는 값 존재 가능 → CHECK 제약 전에 데이터 확인
3. **strt_dt 타임존**: 원본이 "2023-01-01 14:28:25" 형식 → TIMESTAMPTZ로 저장 (UTC 기준)
4. **disp_rtm_sec**: 원본 "00:29" 형식 → 마이그레이션 시 초 단위로 변환

---

**다음 단계**: PLAN_02_DATA_MIGRATION.md 참조
