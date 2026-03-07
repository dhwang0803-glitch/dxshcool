# Phase 1 스키마 설계 근거 문서

**파일**: `Database_Design/schema/DESIGN.md`
**작성일**: 2026-03-07
**참조**: PLAN_01_SCHEMA_DDL.md, PLAN_00_MASTER.md

---

## 1. 테이블별 정규화 검증

### 1-1. "user" 테이블

| 정규화 단계 | 검증 결과 |
|------------|---------|
| 1NF | 모든 컬럼이 원자값. `svod_scrb_cnt_grp`은 "0건", "1건" 등 단일 문자열로 원자값 충족 |
| 2NF | PK가 단일 컬럼(`sha2_hash`)이므로 부분 종속 없음 |
| 3NF | 모든 비키 컬럼이 `sha2_hash`에만 직접 종속. 이행 종속 없음 |

**결론**: 3NF 충족

### 1-2. vod 테이블

| 정규화 단계 | 검증 결과 |
|------------|---------|
| 1NF | 모든 컬럼이 원자값. `genre_detail`, `series_nm` 모두 단일 값 저장 |
| 2NF | PK가 단일 컬럼(`full_asset_id`)이므로 부분 종속 없음 |
| 3NF | `series_nm`이 `ct_cl` 등과 이행 종속 가능성 있음 → **반정규화 허용** (아래 섹션 4 참조) |

**결론**: 실용적 설계상 3NF 완전 충족은 아니나, 반정규화 허용으로 결정

### 1-3. watch_history 테이블

| 정규화 단계 | 검증 결과 |
|------------|---------|
| 1NF | 모든 컬럼이 원자값 |
| 2NF | PK가 단일 컬럼(`watch_history_id`)이므로 부분 종속 없음 |
| 3NF | `completion_rate`는 `use_tms`와 `disp_rtm_sec`으로 계산 가능하나 → **반정규화 허용** (아래 섹션 4 참조) |

**결론**: 실용적 설계상 반정규화 일부 허용

---

## 2. MySQL → PostgreSQL 주요 변환 사항 적용 내역

| MySQL 문법 | PostgreSQL 변환 | 적용 위치 |
|-----------|----------------|---------|
| `AUTO_INCREMENT` | `GENERATED ALWAYS AS IDENTITY` | `watch_history.watch_history_id` |
| `ENGINE=InnoDB` | 제거 | 전체 (PostgreSQL 기본 스토리지 엔진) |
| `DEFAULT CHARSET=utf8mb4` | 제거 | 전체 (DB 레벨에서 설정) |
| `ON UPDATE CURRENT_TIMESTAMP` | 트리거로 구현 | `vod.updated_at` (트리거 `trg_vod_updated_at`) |
| `FULLTEXT INDEX` | `GIN` 인덱스 + `to_tsvector` | `idx_vod_smry_gin` |
| `JSON` | `JSONB` | 해당 컬럼 없음 (현 Phase에서 미사용) |
| `FLOAT` | `REAL` | `inhome_rate`, `ch_hh_avg_month1`, `kids_use_pv_month1`, `use_tms`, `completion_rate`, `satisfaction` |
| `DATE_SUB(NOW(), INTERVAL 30 DAY)` | `NOW() - INTERVAL '30 days'` | 쿼리 레벨 (DDL 미적용) |

### 추가 적용사항

- **`user` 테이블명**: PostgreSQL 예약어이므로 전체 DDL에서 `"user"` (큰따옴표) 사용
- **TIMESTAMPTZ**: `TIMESTAMP WITH TIME ZONE`의 약어. UTC 기준으로 시청 이력 시각 저장

---

## 3. NULL 허용 컬럼 결정 근거 (RAG 처리 예정 컬럼)

### vod.director (VARCHAR(255), NULL 허용)

- **NULL 허용 이유**: 원본 데이터에서 약 313건(0.19%)의 감독 정보 누락
- **처리 계획**: Phase 5 RAG 연동 시 IMDB/Wikipedia API로 보완 예정
- **추적 컬럼**: `rag_processed`, `rag_source`, `rag_processed_at`으로 처리 이력 관리

### vod.smry (TEXT, NULL 허용)

- **NULL 허용 이유**: 원본 데이터에서 약 28건(0.017%)의 줄거리 정보 누락
- **처리 계획**: Phase 5 RAG 연동 시 IMDB/Wikipedia/KMRB API로 보완 예정
- **GIN 인덱스**: `idx_vod_smry_gin`에서 `coalesce(smry, '')`로 NULL 처리하여 인덱스 오류 방지

### RAG 추적 컬럼 설계

| 컬럼 | 타입 | 역할 |
|------|------|------|
| `rag_processed` | BOOLEAN DEFAULT FALSE | 처리 완료 여부 (미처리 레코드 식별용) |
| `rag_source` | VARCHAR(64) | 데이터 출처 (IMDB, Wiki, KMRB 등) |
| `rag_processed_at` | TIMESTAMPTZ | 처리 완료 시각 (감사 로그) |

---

## 4. 반정규화 허용 결정

### 4-1. watch_history.completion_rate (반정규화 허용)

- **이론적 정규화**: `completion_rate = use_tms / disp_rtm_sec`으로 vod 테이블 조인하여 계산 가능
- **반정규화 허용 이유**:
  - 원본 데이터에 이미 계산된 값이 존재 → 마이그레이션 시 직접 적재
  - PostgreSQL `GENERATED ALWAYS AS`는 서브쿼리 참조 불가 (다른 테이블 조인 불가)
  - 3,992,530건 조회 시마다 조인 연산 발생 → 성능 저하 우려
  - `disp_rtm_sec`이 변경될 경우 완주율 재계산 시점 제어 필요 (애플리케이션 레벨 관리)
- **제약조건**: `CHECK (completion_rate >= 0 AND completion_rate <= 1)`로 범위 보장

### 4-2. vod.series_nm (반정규화 허용)

- **이론적 정규화**: series 테이블 분리 후 FK 참조
- **반정규화 허용 이유**:
  - 추천 시스템의 조회 단위가 VOD 단위 → 시리즈 테이블 조인 필요성 낮음
  - 166,159개 VOD 중 series가 있는 VOD 비율과 series 정보 갱신 빈도가 낮음
  - 현 단계(Phase 1)에서는 단순성 우선 → Phase 4 확장 시 재검토 가능

---

## 5. 인덱스 설계 근거 (우선순위별)

### HIGH 우선순위 - watch_history (5개)

| 인덱스명 | 컬럼 | 근거 |
|---------|------|------|
| `idx_wh_user_id` | `user_id_fk` | 사용자별 시청이력 조회 - 추천 시스템 핵심 쿼리. 242,702 사용자 × 평균 16.45건 |
| `idx_wh_vod_id` | `vod_id_fk` | VOD별 시청 통계 - 인기 VOD 산출, 협업 필터링 연산 |
| `idx_wh_strt_dt` | `strt_dt` | 날짜 범위 분석 - 최근 N일 시청이력 필터링 |
| `idx_wh_satisfaction` | `satisfaction` | 만족도 기반 추천 - ORDER BY satisfaction DESC 쿼리 |
| `idx_wh_user_strt` | `(user_id_fk, strt_dt)` | 사용자별 시간순 조회 복합 인덱스 - `idx_wh_user_id` 단독 대비 정렬 없이 처리 가능 |

### MEDIUM 우선순위 - vod (4개)

| 인덱스명 | 컬럼 | 근거 |
|---------|------|------|
| `idx_vod_ct_cl` | `ct_cl` | 콘텐츠 타입별 필터링 (영화/라이프/키즈 등) - 추천 필터 조건 |
| `idx_vod_genre` | `genre` | 장르 기반 추천 필터링 |
| `idx_vod_provider` | `provider` | 제공사별 콘텐츠 조회 |
| `idx_vod_smry_gin` | `smry (GIN)` | MySQL FULLTEXT INDEX 대체. `to_tsvector`로 한국어 형태소 기반 검색. `coalesce(smry, '')`로 NULL 안전 처리 |

**GIN 인덱스 텍스트 설정 결정**:
- 운영 환경에 한국어 형태소 분석기(`korean` 텍스트 설정)가 설치된 경우:
  `to_tsvector('korean', coalesce(smry, ''))`
- 미설치 환경 또는 기본 PostgreSQL 환경:
  `to_tsvector('simple', coalesce(smry, ''))` (현재 적용)

### LOW 우선순위 - "user" (2개)

| 인덱스명 | 컬럼 | 근거 |
|---------|------|------|
| `idx_user_age_grp` | `age_grp10` | 연령대별 사용자 세그먼트 분석 - 추천 모델 특성 추출 |
| `idx_user_nfx` | `nfx_use_yn` | Netflix 이용 여부 세그먼트 - 경쟁 서비스 분석 |

---

## 6. 트리거 설계 근거

### update_updated_at_column() 함수

- **목적**: MySQL의 `ON UPDATE CURRENT_TIMESTAMP` 동작을 PostgreSQL에서 재현
- **설계 결정**:
  - 함수를 별도로 분리하여 재사용 가능하게 설계 (다른 테이블에도 `CREATE TRIGGER`만으로 적용 가능)
  - `BEFORE UPDATE`로 설정하여 `NEW.updated_at`에 현재 시각 할당 후 행 저장
  - `plpgsql` 언어 사용 (PostgreSQL 표준)

### trg_vod_updated_at 트리거

- **적용 대상**: vod 테이블 (RAG 처리 후 정보 갱신 추적 필요)
- **적용 시점**: `BEFORE UPDATE`, `FOR EACH ROW`
- **watch_history 미적용 이유**: 시청이력은 삽입 전용(`INSERT`)으로 설계. 갱신 시나리오 없음
- **"user" 미적용 이유**: `last_active_at`은 애플리케이션에서 명시적으로 갱신하는 것이 의도적. 자동 갱신 시 오해 소지 있음

---

## 7. 파일 실행 순서

```
1. create_tables.sql   -- 테이블 생성, 트리거 함수/적용, 코멘트
2. create_indexes.sql  -- 인덱스 생성 (테이블 선행 필요)
```

### 전체 실행 명령어

```bash
psql -U <username> -d <dbname> \
  -f Database_Design/schema/create_tables.sql \
  -f Database_Design/schema/create_indexes.sql
```

---

## 8. 테스트 커버리지

`Database_Design/tests/test_schema.sql` 기준 60개 테스트:

| 섹션 | 범위 | 건수 |
|------|------|------|
| 섹션 1 | 테이블 존재 확인 | T01~T03 (3건) |
| 섹션 2 | "user" 컬럼/타입 확인 | T04~T14 (11건) |
| 섹션 3 | vod 컬럼/타입 확인 | T15~T32 (18건) |
| 섹션 4 | watch_history 컬럼/타입 확인 | T33~T43 (11건) |
| 섹션 5 | 제약조건 확인 | T44~T47 (4건) |
| 섹션 6 | 인덱스 존재 확인 | T48~T57 (10건) |
| 섹션 7 | 트리거 확인 및 동작 검증 | T58~T60 (3건) |
