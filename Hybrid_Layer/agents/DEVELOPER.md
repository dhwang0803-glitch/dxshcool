# Hybrid_Layer Developer Agent 지시사항

## 역할
Test Writer Agent가 작성한 테스트를 통과하는 최소한의 코드를 구현한다 (TDD Green 단계).
과도한 설계나 불필요한 기능을 추가하지 않는다.

---

## 구현 원칙

1. **테스트 통과 최우선**: 현재 실패하는 테스트를 통과시키는 것만 구현한다
2. **최소 구현**: 테스트를 통과하는 가장 단순한 코드를 작성한다
3. **PLAN 준수**: 해당 Phase의 PLAN 파일 내용을 벗어나지 않는다
4. **CLAUDE.md 우선**: `Hybrid_Layer/CLAUDE.md`의 데이터 플로우·시리즈 중복제거·배너 구조 규칙을 반드시 준수한다

---

## Phase별 구현 파일 위치

| Phase | 구현 파일 | 위치 |
|-------|----------|------|
| Phase 1 | `tag_builder.py` | `Hybrid_Layer/src/` |
| Phase 2 | `preference_builder.py` | `Hybrid_Layer/src/` |
| Phase 3 | `reranker.py` | `Hybrid_Layer/src/` |
| Phase 4 | `shelf_builder.py` | `Hybrid_Layer/src/` |
| 공통 | `db.py` | `Hybrid_Layer/src/` |
| 파이프라인 | `run_pipeline.py` | `Hybrid_Layer/scripts/` |

**`Hybrid_Layer/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

---

## 환경변수 로드 방식

```python
from dotenv import load_dotenv
import os

load_dotenv('.env')  # 프로젝트 루트의 .env (VPC 접속 정보)
```

---

## DB 연결 방식

```python
from dotenv import load_dotenv
import psycopg2, os

load_dotenv('.env')

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD')
)
```

---

## 🗄️ DB 접근 코드 작성 원칙 (MANDATORY — VPC 네트워크 I/O 최소화)

> VPC PostgreSQL은 원격 서버다. 쿼리 1회당 네트워크 왕복이 발생한다.
> 루프 안에 DB 쿼리를 넣으면 수백~수천 번 왕복이 생겨 파이프라인이 치명적으로 느려진다.
> **코드 작성 전 반드시 DB 왕복 수를 계획하고 주석으로 명시한다.**

### ❌ 금지 패턴 — N+1 쿼리 (루프 안 DB 쿼리)

```python
# 절대 금지: 루프 안에서 fetch
for user_id in user_ids:                                      # 유저 수만큼
    cur.execute("SELECT ... WHERE user_id = %s", (user_id,))  # 왕복 발생!
    rows = cur.fetchall()
    cur.execute("INSERT INTO ... VALUES (%s)", (...))          # 왕복 발생!
```

### ✅ 올바른 패턴 — 전체 dump → Python 계산 → 배치 INSERT

```python
# DB 왕복 계획: 읽기 N회 + INSERT ~수십 회 = 총 ~수십 회

# 1. 루프 밖에서 전체 데이터를 한 번에 dump (DB 쿼리 1회)
cur.execute("SELECT user_id, col1, col2 FROM table WHERE ...")
all_data = {row[0]: row for row in cur.fetchall()}

# 2. 순수 Python 계산 (DB 왕복 없음)
results = []
for user_id in user_ids:
    results.append(compute(all_data.get(user_id)))

# 3. 배치 INSERT — 행 단위 INSERT 절대 금지, 10,000행 단위 배치
BATCH = 10_000
for i in range(0, len(results), BATCH):
    batch = results[i:i + BATCH]
    args = ",".join(cur.mogrify("(%s,%s)", r).decode() for r in batch)
    cur.execute(f"INSERT INTO target VALUES {args} ON CONFLICT ...")
    conn.commit()
```

### 구현 전 DB 왕복 수 계획표 작성 (필수)

코드 작성 전 아래 형식의 주석을 함수 docstring에 포함한다:

```python
"""
DB 왕복 계획:
  읽기: CF 후보 dump (1회) + user_preference dump (1회) + vod_tag dump (1회)
  쓰기: INSERT 배치 (~25회, 10,000행 단위)
  총계: ~28회  ← 100회 이상이면 설계 재검토
"""
```

### 설계 판단 기준

| 총 DB 왕복 수 | 판단 | 조치 |
|--------------|------|------|
| ~50회 이하 | ✅ 양호 | 그대로 구현 |
| 50~100회 | ⚠️ 주의 | 추가 dump 통합 검토 |
| 100회 초과 | ❌ 재설계 | 루프 안 쿼리 제거 필수 |

---

## Phase별 구현 체크리스트

### Phase 1 — tag_builder.py

```
DB 왕복 계획:
  읽기: vod 전체 dump (1회)
  쓰기: vod_tag 배치 INSERT (~수십 회)
  총계: ~수십 회

구현 항목:
1. public.vod에서 director, cast_lead, cast_guest, genre, genre_detail 컬럼 읽기
2. 각 컬럼 값을 tag_category/tag_value/confidence로 변환
3. confidence는 TMDB 기반 (컬럼별 고정값 또는 계산값)
4. public.vod_tag에 ON CONFLICT DO NOTHING으로 배치 INSERT
5. tag_category 허용값: 'director', 'actor_lead', 'actor_guest', 'genre', 'genre_detail'
```

### Phase 2 — preference_builder.py

```
DB 왕복 계획:
  읽기: watch_history dump (1회) + vod_tag dump (1회)
  쓰기: user_preference 배치 UPSERT (~수십 회)
  총계: ~수십 회

구현 항목:
1. watch_history × vod_tag 매칭 → user × tag affinity 계산
2. affinity = completion_rate 가중 평균 (watch_count 반영)
3. public.user_preference에 ON CONFLICT DO UPDATE로 배치 UPSERT
4. test_mode: is_test 유저 분기 → user_preference_test 테이블 적재
```

### Phase 3 — reranker.py

```
DB 왕복 계획:
  읽기: vod_recommendation dump (1회) + user_preference dump (1회) + vod_tag dump (1회)
  쓰기: hybrid_recommendation DELETE (1회) + 배치 INSERT (~수십 회)
  총계: ~수십 회

구현 항목:
1. CF 후보 전체 dump (COLLABORATIVE 타입, user_id_fk IS NOT NULL)
   ※ Vector_Search CONTENT_BASED는 user_id=NULL → 포함하지 않음
2. user_preference 전체 dump
3. 후보 VOD vod_tag dump (unique vod_id 목록 기준)
4. hybrid_score = β × original_score + (1-β) × tag_overlap_score
   - tag_overlap_score = mean(상위 top_k_tags개 matched affinity)
5. 상위 top_n건 + explanation_tags(affinity 내림차순 최대 5개) 생성
6. serving.hybrid_recommendation에 DELETE → 배치 INSERT
7. test_mode: vod_recommendation_test → hybrid_recommendation_test
8. 시리즈 중복제거 없음 (CF_Engine이 이미 처리)
```

### Phase 4 — shelf_builder.py

```
DB 왕복 계획:
  읽기: user_preference dump (1회) + tag_vod_cache 빌드 (1회)
        + watch_history dump (1회) + user age_grp10 dump (1회)
        + age_grp별 cold tag 조회 (~9회)
        + cold 전용 태그 VOD 캐시 (0~1회)
  쓰기: tag_recommendation DELETE (1회) + 배치 INSERT (~수십 회)
  총계: ~15~20회

구현 항목:
1. user_preference 전체 dump (SQL ROW_NUMBER로 카테고리별 순위 미리 계산)
2. 전체 unique tags → tag_vod_cache 한 번에 빌드
   ※ unnest(%s::varchar[], %s::varchar[]) 패턴으로 배열 조인
3. watch_history 전체 dump (시청 제외 필터링용)
4. Cold start: age_grp10 + 연령대별 인기 genre_detail 태그 조회
5. 순수 Python 선반 조립:
   - 카테고리별 슬롯: genre 3, genre_detail 3, director 2, actor_lead 2, actor_guest 2
   - 10개 미달 태그 스킵 → 후순위 태그로 자동 대체
   - 시리즈 중복제거 (is_episode_level 조건 참고)
   - Cold start fallback: 빈 슬롯 → 연령대 인기 genre_detail (최대 5개)
6. serving.tag_recommendation에 DELETE → 배치 INSERT
7. test_mode: tag_recommendation_test 적재

시리즈 중복제거 기준:
  is_episode_level = (cat == "actor_guest" and ct_cl == "TV 연예/오락")
  is_episode_level이면 에피소드 단위 유지 (중복제거 제외)
  director는 시리즈 전체를 연출하므로 항상 시리즈 기준 중복제거
  그 외 모든 경우 → series_nm 기준 중복제거
```

---

## 테스터 격리 (test_mode)

```python
# test_mode=True: is_test=TRUE 유저 → _test 테이블
# test_mode=False: is_test=FALSE 유저 → 실 테이블

src_table = "serving.vod_recommendation_test" if test_mode else "serving.vod_recommendation"
dst_table = "serving.hybrid_recommendation_test" if test_mode else "serving.hybrid_recommendation"
is_test_filter = "AND u.is_test = TRUE" if test_mode else "AND u.is_test = FALSE"
```

Phase 1 (vod_tag)은 전체 공용 데이터 → test_mode 무관하게 항상 실 테이블 사용.

---

## 구현 완료 후 자가 점검

- [ ] 하드코딩된 API 키, IP, 비밀번호 없음
- [ ] os.getenv() 기본값에 실제 인프라 정보 없음 (포트 5432 제외)
- [ ] **루프 안에 `cur.execute` + `fetchall()` 없음 (N+1 쿼리 없음)**
- [ ] **INSERT는 행 단위가 아닌 배치 (mogrify 또는 execute_values)**
- [ ] **DB 왕복 계획표를 docstring에 명시함**
- [ ] `WHERE {column} IS NULL` 또는 DELETE → INSERT 패턴으로 기존 값 보호/갱신
- [ ] test_mode 분기로 테스터 격리 처리
- [ ] 시리즈 중복제거 규칙 (CLAUDE.md 기준) 준수
- [ ] 10개 미달 태그 스킵 → 후순위 대체 로직 구현 (Phase 4)
- [ ] Cold start fallback 최대 5개 제한 준수 (Phase 4)
