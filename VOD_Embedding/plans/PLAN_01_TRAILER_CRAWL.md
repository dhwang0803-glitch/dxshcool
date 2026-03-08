# PLAN_01: YouTube 트레일러 수집

**브랜치**: VOD_Embedding
**스크립트**: `pipeline/crawl_trailers.py`
**입력**: vod 테이블 (`full_asset_id`, `asset_nm`, `ct_cl`, `genre`)
**출력**: `trailers/*.webm`, `data/crawl_status.json`

---

## 목표

vod 테이블 45,000개 중 YouTube 트레일러 수집 가능한 대상에 대해:
1. YouTube 검색 쿼리 생성
2. yt-dlp로 영상 다운로드 (최저 화질, 최대 5분)
3. 결과를 체크포인트 파일에 기록 (중단/재시작 지원)

예상 성공률: 60~80% (국내 드라마/예능/키즈 제외 시 더 높음)

---

## 처리 대상 필터 (ct_cl 기준)

```python
EXCLUDE_CT_CL = {'홈쇼핑'}          # 상품 판매 — 트레일러 없음
INCLUDE_CT_CL = {'영화', '드라마', '예능', '애니메이션', '다큐멘터리', '스포츠'}
# 키즈: 별도 검토 후 포함 여부 결정 (기본 포함)
```

SQL 필터:
```sql
SELECT full_asset_id, asset_nm, ct_cl, genre
FROM vod
WHERE ct_cl NOT IN ('홈쇼핑')
ORDER BY full_asset_id;
```

---

## YouTube 검색 쿼리 전략

### 우선순위 쿼리 (순서대로 시도)

```python
def build_search_queries(asset_nm: str, genre: str, ct_cl: str) -> list[str]:
    queries = []

    # 1순위: 한국어 + 예고편
    queries.append(f"{asset_nm} 예고편")

    # 2순위: 한국어 + trailer
    queries.append(f"{asset_nm} trailer")

    # 3순위: 장르별 맞춤 검색
    if ct_cl == '영화':
        queries.append(f"{asset_nm} official trailer")
        queries.append(f"{asset_nm} 공식 예고편")
    elif ct_cl in ('드라마', '예능'):
        queries.append(f"{asset_nm} 하이라이트")
        queries.append(f"{asset_nm} 1회")

    return queries
```

### 검색 결과 신뢰도 기준
- 영상 길이: **30초 ~ 5분** (트레일러 범위)
- 제목에 VOD명 포함 여부 확인
- 조회수 기준 없음 (신작/비인기 콘텐츠 포함)

---

## 다운로드 설정

```python
YDL_OPTS = {
    'format': 'worst[ext=webm]/worst',    # 최저 화질 (디스크 절약)
    'outtmpl': 'trailers/%(id)s.%(ext)s',
    'quiet': True,
    'no_warnings': True,
    'match_filter': check_duration,        # 30초~5분 필터
    'max_filesize': 50 * 1024 * 1024,     # 50MB 상한
    'retries': 3,
    'socket_timeout': 30,
}

def check_duration(info, incomplete):
    duration = info.get('duration') or 0
    if duration < 30:
        return "영상이 너무 짧음 (30초 미만)"
    if duration > 300:
        return "영상이 너무 김 (5분 초과)"
    return None
```

---

## 체크포인트 구조 (`data/crawl_status.json`)

```json
{
  "last_updated": "2026-03-08T12:00:00",
  "total": 45000,
  "processed": 12500,
  "success": 9800,
  "failed": 2700,
  "vods": {
    "VOD001234": {
      "status": "success",
      "filename": "dQw4w9WgXcQ.webm",
      "query_used": "어바웃 타임 예고편",
      "duration_sec": 142,
      "downloaded_at": "2026-03-08T10:30:00"
    },
    "VOD001235": {
      "status": "failed",
      "reason": "no_result",
      "tried_queries": ["홍길동 예고편", "홍길동 trailer"],
      "failed_at": "2026-03-08T10:31:00"
    },
    "VOD001236": {
      "status": "skipped",
      "reason": "ct_cl_excluded"
    }
  }
}
```

---

## 속도 제어

- **요청 간격**: 1.5~3초 랜덤 sleep (YouTube 차단 방지)
- **배치 단위**: 100개마다 체크포인트 저장
- **에러 대기**: 429 Too Many Requests → 60초 대기 후 재시도

```python
import time, random

def rate_limited_download(vod_id, queries, ydl_opts):
    time.sleep(random.uniform(1.5, 3.0))
    # ... yt-dlp 실행
```

---

## 실행 방법

```bash
# 환경 활성화
conda activate myenv

# 전체 실행 (중단 후 재시작 시 자동으로 이어서 진행)
python pipeline/crawl_trailers.py

# 특정 ct_cl만 처리
python pipeline/crawl_trailers.py --ct-cl 영화 드라마

# 드라이런 (실제 다운로드 없이 검색만)
python pipeline/crawl_trailers.py --dry-run --limit 10

# 진행 현황 확인
python pipeline/crawl_trailers.py --status
```

---

## 예상 소요 시간

| 항목 | 수치 |
|------|------|
| 대상 VOD | ~40,000개 (홈쇼핑 제외) |
| 건당 처리 시간 | 평균 5초 (검색 2초 + 다운로드 3초) |
| 총 소요 시간 | ~56시간 (2~3일) |
| 트레일러 디스크 사용량 | ~80GB (평균 2MB/개) |

> 오버나이트 + 주말 연속 실행 권장

---

**다음**: PLAN_02_BATCH_EMBED.md
