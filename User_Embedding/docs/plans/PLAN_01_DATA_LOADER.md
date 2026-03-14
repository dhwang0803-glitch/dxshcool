# PLAN_01: watch_history 데이터 로더

**목표**: DB `watch_history` 테이블에서 유저별 시청 이력을 로드하여 파이프라인에 공급

---

## 입출력

| 항목 | 내용 |
|------|------|
| **입력** | DB `watch_history` 테이블 |
| **출력** | `{user_id: [(asset_id, completion_rate), ...]}` |

---

## DB 쿼리

```sql
SELECT user_id, asset_id, completion_rate
FROM watch_history
WHERE completion_rate > 0
ORDER BY user_id, asset_id;
```

> `completion_rate = 0` (시청 시작만 하고 바로 종료)은 가중치가 0이므로 제외.

---

## 구현 파일: `src/data_loader.py`

```python
def load_watch_history(conn) -> dict[str, list[tuple[str, float]]]:
    """
    Returns:
        {user_id: [(asset_id, completion_rate), ...]}
    """
```

---

## 배치 처리 (대용량 대응)

- 전체 watch_history 건수가 많을 경우 `LIMIT / OFFSET` 또는 커서(server-side cursor) 방식 사용
- `psycopg2.extras.server_side_cursor` 권장 (메모리 절약)

---

## 예외 처리

| 상황 | 처리 |
|------|------|
| `watch_history` 테이블 없음 | `psycopg2.errors.UndefinedTable` → 오류 메시지 출력 후 종료 |
| 데이터 0건 | 빈 dict 반환 + 경고 로그 |
| completion_rate NULL | WHERE 조건에서 자동 제외 (`NULL > 0` = false) |

---

## 검증

```python
history = load_watch_history(conn)

# 유저 수 확인
print(f"총 유저 수: {len(history):,}")

# 유저당 평균 시청 VOD 수
avg = sum(len(v) for v in history.values()) / len(history)
print(f"유저당 평균 시청 VOD: {avg:.1f}건")

# completion_rate 범위 확인 (0 < rate <= 1.0)
all_rates = [r for items in history.values() for _, r in items]
assert all(0 < r <= 1.0 for r in all_rates), "completion_rate 범위 오류"
```

---

**다음**: PLAN_02_VOD_LOADER.md
