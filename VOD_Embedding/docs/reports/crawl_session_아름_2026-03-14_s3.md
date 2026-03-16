# crawl_trailers_아름.py 세션 리포트 — S3

- **작성일**: 2026-03-14
- **작성자**: 박아름
- **브랜치**: VOD_Embedding

---

## 1. 세션 목표

S2 재시작 이후 패밀리가 떴다 전 회차 FAIL 대량 발생 원인 분석 및 수정.

---

## 2. 발견된 버그 (2가지 복합 원인)

### 버그 1: DURATION_MAX_SEC = 600 (10분) 너무 타이트

SBS 공식 채널 "SBS 옛날 예능 - 빽능"은 에피소드 하이라이트를 약 11분 단위로 업로드.

| 항목 | 수치 |
|------|------|
| YouTube 실제 영상 | "[패밀리가 떴다] 오빠하고 나하고~ 재석 어부바 효리 \| EP.13" |
| 실제 duration | 11:43 = **703초** |
| 기존 필터 상한 | **600초** |
| 결과 | 703 > 600 → 전 회차 거부 |

**수정**: `DURATION_MAX_SEC` 600 → **900** (15분)

---

### 버그 2: EP.N 형식 정규식 불일치

YouTube 제목 형식이 `EP.13` (점 포함)인데 기존 `has_episode_num` 정규식이 이를 처리 못함.

| 패턴 | EP13 | EP.13 |
|------|------|-------|
| 기존: `EP0*13` | ✅ | ❌ |
| 수정: `EP\.?0*13` | ✅ | ✅ |

**수정**: `E0*{n}\b\|EP0*{n}\b` → `E\.?0*{n}\b\|EP\.?0*{n}\b`

---

## 3. 수정 파일

`VOD_Embedding/scripts/crawl_trailers_아름.py` (gitignore — 로컬 전용)

```python
# 변경 전
DURATION_MAX_SEC = 600

# 변경 후
DURATION_MAX_SEC = 900
```

```python
# 변경 전 (has_episode_num 내부)
rf'E0*{ep_int}\b|EP0*{ep_int}\b|#{ep_int}\b|{ep_int}회|{ep_int}화'

# 변경 후
rf'E\.?0*{ep_int}\b|EP\.?0*{ep_int}\b|#{ep_int}\b|{ep_int}회|{ep_int}화'
```

---

## 4. 진행 현황 (S3 재시작 전 기준)

S2 리포트(2026-03-14 00:24) 이후 계속 실행 → 1,060건 추가 처리 중 패밀리가 떴다 연속 FAIL 확인.

| 항목 | 수치 |
|------|------|
| S2 누적 처리 | 4,996건 (52.2%) |
| S3 재시작 시점 추가 처리 | ~1,060건 |
| 패밀리가 떴다 FAIL 건수 | 다수 (20회, 24회, 32회, 50회, 06회, 13회 등 확인) |

---

## 5. FAIL 원인별 누적 분류

| 원인 | 대표 프로그램 | 대응 방안 |
|------|-------------|----------|
| duration 초과 (703s) | 패밀리가 떴다 | ✅ S3에서 수정 완료 (900s) |
| EP.N 정규식 불일치 | 패밀리가 떴다 | ✅ S3에서 수정 완료 |
| YouTube 원본 부재 | 위대한탄생 시즌2, 나는가수다2 | 2차 재시도 스킵 |
| KBS 날짜형식 제목 | 우리동네 예체능 등 | 2차 재시도 — air_date→YYMMDD + ep_int 완화 |
| 특정 yt_id unavailable | 패밀리가 떴다 '예고편' fallback | 자동 continue 처리됨 |

---

## 6. 브랜치 동기화

| 브랜치 | 결과 |
|--------|------|
| `main` | `a706d06` → `3f14ab5` (+47 커밋) pull 완료 |
| `User_Embedding` | `356caa1` → `16f8427` (+153 커밋) pull 완료 |
| 나머지 (API_Server, Database_Design, RAG, Poster_Collection) | 최신 상태 유지 |

---

## 7. 다음 단계

1. S3 재시작 후 패밀리가 떴다 회차 수집 확인
2. `crawl_trailers_아름.py` 1차 완료 대기
3. failed 항목 2차 분류 — KBS 날짜형식 / 원본 부재 / 기타
4. 2차 재시도 스크립트 작성 (air_date→YYMMDD, ep_int 완화)
5. `batch_embed_아름.py --delete-after-embed` 실행
6. `data/embeddings_아름_v2.parquet` → 조장(황대원) 전달
