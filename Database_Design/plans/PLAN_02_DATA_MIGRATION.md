# Phase 2: 데이터 마이그레이션 계획

**단계**: Phase 2 / 5
**목표**: CSV 원본 데이터를 PostgreSQL로 안전하게 적재
**산출물**: `migration/migrate.py`, `migration/validate_data.py`

---

## 1. 마이그레이션 전략

### 적재 순서 (FK 의존성 고려)
```
1. user 테이블 적재     (242,702건, 독립 테이블)
2. vod 테이블 적재      (166,159건, 독립 테이블)
3. watch_history 적재   (3,992,530건, user + vod 참조)
```

### 배치 처리 전략
- 단건 INSERT는 성능 문제 → `COPY` 명령 또는 bulk insert 사용
- PostgreSQL `COPY FROM STDIN` 또는 `psycopg2.extras.execute_values` 활용
- watch_history는 10,000건씩 배치 처리

---

## 2. 데이터 변환 규칙

### USER 테이블 변환

| 원본 컬럼 | 변환 | 설명 |
|----------|------|------|
| sha2_hash | 그대로 사용 | PRIMARY KEY |
| AGE_GRP10 | 소문자 컬럼명으로 저장 | "60대", "50대" 등 |
| INHOME_RATE | REAL로 캐스팅 | 0.0 ~ 100.0 |
| SVOD_SCRB_CNT_GRP | 그대로 저장 | "0건", "1건" 등 |
| PAID_CHNL_CNT_GRP | 그대로 저장 | "0건", "1건" 등 |
| CH_HH_AVG_MONTH1 | REAL로 캐스팅 | |
| KIDS_USE_PV_MONTH1 | REAL로 캐스팅 | |
| NFX_USE_YN | "Y" → TRUE, "N" → FALSE | BOOLEAN 변환 |

### VOD 테이블 변환

| 원본 컬럼 | 변환 | 설명 |
|----------|------|------|
| full_asset_id | 그대로 사용 | PRIMARY KEY |
| asset_nm | 그대로 저장 | |
| CT_CL | 소문자 컬럼명으로 저장 | |
| disp_rtm | 원본 형식 저장 ("HH:MM" 또는 "HH:MM:SS") | |
| disp_rtm_sec | 초 단위로 변환하여 저장 | "01:21" → 4860 |
| genre | 그대로 저장 | |
| director | NULL 허용 | 313건 NULL 존재 |
| asset_prod | 그대로 저장 | |
| smry | NULL 허용 | 28건 NULL, "-" 처리 주의 |
| provider | 그대로 저장 | |
| genre_detail | 그대로 저장 | |
| series_nm | NULL 허용 | |

### disp_rtm 변환 함수 (Python)
```python
def parse_disp_rtm(disp_rtm_str: str) -> int:
    """
    "HH:MM" 또는 "HH:MM:SS" 형식을 초 단위로 변환
    예: "01:21" → 4860, "00:29" → 1740
    """
    if pd.isna(disp_rtm_str) or disp_rtm_str == '-':
        return 0
    parts = str(disp_rtm_str).strip().split(':')
    try:
        if len(parts) == 2:
            h, m = int(parts[0]), int(parts[1])
            return h * 3600 + m * 60
        elif len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return h * 3600 + m * 60 + s
    except (ValueError, TypeError):
        return 0
    return 0
```

### WATCH_HISTORY 테이블 변환

| 원본 컬럼 | 변환 | 설명 |
|----------|------|------|
| sha2_hash | user_id_fk로 저장 | FK 참조 |
| full_asset_id | vod_id_fk로 저장 | FK 참조 |
| strt_dt | TIMESTAMPTZ로 파싱 | "2023-01-01 14:28:25" |
| use_tms | REAL로 캐스팅 | 초 단위 |
| completion_rate | REAL로 캐스팅 | 0 ~ 1 범위 |
| satisfaction | REAL로 캐스팅 | 0 ~ 1 범위 |

---

## 3. 데이터 품질 검사 (마이그레이션 전)

### 사전 검사 항목 (validate_data.py)

```python
# 1. 중복 키 확인
assert user_df['sha2_hash'].nunique() == len(user_df), "USER 중복 sha2_hash 존재"
assert vod_df['full_asset_id'].nunique() == len(vod_df), "VOD 중복 full_asset_id 존재"

# 2. FK 무결성 확인
wh_user_ids = set(watch_history_df['sha2_hash'].unique())
user_ids = set(user_df['sha2_hash'].unique())
orphan_users = wh_user_ids - user_ids
assert len(orphan_users) == 0, f"WATCH_HISTORY에 USER 없는 sha2_hash 존재: {len(orphan_users)}건"

wh_vod_ids = set(watch_history_df['full_asset_id'].unique())
vod_ids = set(vod_df['full_asset_id'].unique())
orphan_vods = wh_vod_ids - vod_ids
assert len(orphan_vods) == 0, f"WATCH_HISTORY에 VOD 없는 full_asset_id 존재: {len(orphan_vods)}건"

# 3. completion_rate 범위 확인
assert watch_history_df['completion_rate'].between(0, 2).all(), "completion_rate 이상값"
# 범위 초과 시 1.0으로 클리핑

# 4. NULL 현황 출력
print("=== NULL 현황 ===")
print(vod_df[['director', 'smry']].isnull().sum())
```

---

## 4. migrate.py 구조

```python
"""
VOD 추천 시스템 - PostgreSQL 마이그레이션 스크립트
CSV 데이터 → PostgreSQL 3개 테이블 적재

사용법:
    python migrate.py --host localhost --port 5432 --db vod_db --user postgres
    python migrate.py --config config.yaml  # 설정 파일 방식
"""

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from sqlalchemy import create_engine
import logging
from pathlib import Path

# 설정
DATA_DIR = Path("../data/prepared_data")
BATCH_SIZE = 10_000  # watch_history 배치 크기

# 적재 순서
def main():
    engine = create_engine(CONNECTION_STRING)

    # 1. USER 적재
    load_users(engine)

    # 2. VOD 적재
    load_vods(engine)

    # 3. WATCH_HISTORY 적재 (배치)
    load_watch_history(engine)

    # 4. 검증
    validate_counts(engine)

def load_users(engine):
    """USER 테이블 적재"""
    df = pd.read_csv(DATA_DIR / "user_table.csv")
    # 변환
    df['nfx_use_yn'] = df['NFX_USE_YN'].map({'Y': True, 'N': False})
    # 컬럼 소문자 변환 및 매핑
    df = df.rename(columns={
        'AGE_GRP10': 'age_grp10',
        'INHOME_RATE': 'inhome_rate',
        ...
    })
    df.to_sql('user', engine, if_exists='append', index=False, method='multi')

def load_watch_history(engine):
    """WATCH_HISTORY 배치 적재"""
    for chunk in pd.read_csv(DATA_DIR / "watch_history_table.csv",
                              chunksize=BATCH_SIZE):
        chunk = transform_watch_history(chunk)
        chunk.to_sql('watch_history', engine, if_exists='append',
                     index=False, method='multi')
        logging.info(f"적재 완료: {len(chunk)}건")
```

---

## 5. 성능 최적화 (마이그레이션 시)

### PostgreSQL COPY 명령 활용 (대용량 최적화)
```python
# psycopg2 COPY 방식 (가장 빠름)
with open('watch_history.csv', 'r') as f:
    cursor.copy_expert(
        "COPY watch_history (user_id_fk, vod_id_fk, strt_dt, use_tms, completion_rate, satisfaction) "
        "FROM STDIN WITH CSV HEADER",
        f
    )
```

### 인덱스 비활성화 후 적재 (선택적 최적화)
```sql
-- 대용량 초기 적재 시 인덱스를 나중에 생성하면 빠름
-- 1. 테이블 생성 (인덱스 없이)
-- 2. 데이터 COPY
-- 3. 인덱스 생성 (CONCURRENTLY 사용 가능)
CREATE INDEX CONCURRENTLY idx_wh_user_id ON watch_history (user_id_fk);
```

---

## 6. 마이그레이션 후 검증

### 데이터 건수 확인
```sql
SELECT
    (SELECT COUNT(*) FROM "user") AS user_count,
    (SELECT COUNT(*) FROM vod) AS vod_count,
    (SELECT COUNT(*) FROM watch_history) AS watch_count;
-- 기대값: user=242702, vod=166159, watch=3992530
```

### FK 무결성 확인
```sql
-- WATCH_HISTORY에서 USER 없는 레코드
SELECT COUNT(*) FROM watch_history wh
LEFT JOIN "user" u ON wh.user_id_fk = u.sha2_hash
WHERE u.sha2_hash IS NULL;
-- 기대값: 0

-- WATCH_HISTORY에서 VOD 없는 레코드
SELECT COUNT(*) FROM watch_history wh
LEFT JOIN vod v ON wh.vod_id_fk = v.full_asset_id
WHERE v.full_asset_id IS NULL;
-- 기대값: 0
```

### 만족도 분포 확인
```sql
SELECT
    COUNT(*) FILTER (WHERE satisfaction = 0) AS zero_sat,
    COUNT(*) FILTER (WHERE satisfaction > 0 AND satisfaction <= 0.2) AS low,
    COUNT(*) FILTER (WHERE satisfaction > 0.2 AND satisfaction <= 0.6) AS medium,
    COUNT(*) FILTER (WHERE satisfaction > 0.6) AS high
FROM watch_history;
-- 기대값 (설계요구사항.md): zero=1006961, low=653230, medium=766208, high=1566131
```

---

## 7. 에러 처리

| 에러 상황 | 처리 방법 |
|----------|---------|
| FK 위반 (orphan watch_history) | 로그 기록 후 해당 레코드 스킵 |
| completion_rate > 1.0 | 1.0으로 클리핑 후 적재 |
| disp_rtm 파싱 실패 | 0 또는 NULL 저장 후 로그 |
| 중복 레코드 (unique 위반) | ON CONFLICT DO NOTHING |

```sql
-- 중복 처리 예시
INSERT INTO watch_history (user_id_fk, vod_id_fk, strt_dt, use_tms, completion_rate, satisfaction)
VALUES (...)
ON CONFLICT (user_id_fk, vod_id_fk, strt_dt) DO NOTHING;
```

---

**이전 단계**: PLAN_01_SCHEMA_DDL.md
**다음 단계**: PLAN_03_PERFORMANCE_TEST.md
