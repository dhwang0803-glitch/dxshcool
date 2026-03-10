# Approach B (v8 + 병렬처리) 파일럿 결과 요약

> 방식: TMDB 시리즈 캐시 + ct_cl 분기 + KMDB 폴백 + DATA_GO(영상물등급위원회) + **JustWatch GraphQL**
> + **ThreadPoolExecutor(20) 병렬처리** + API별 BoundedSemaphore + KMDB‖JW 내부 병렬
> 샘플: 100건 층화추출 | 실행일: 2026-03-10 | 오류: 0건

---

## 버전별 성공률 변화

| 컬럼         | v5 (TMDB+KMDB) | v7 (+ DATA_GO + ep폴백) | v8 (+ JustWatch) | v7→v8 개선 |
|------------|---------------:|------------------------:|-----------------:|----------:|
| cast_lead  | 64%            | 72%                     | **81%**          | +9건       |
| rating     | 54%            | 60%                     | **67%**          | +7건       |
| release_date | 76%          | 76%                     | **76%**          | —         |
| director   | 54%            | 57%                     | **68%**          | +11건      |
| smry       | 74%            | 74%                     | **84%**          | +10건      |
| series_nm  | 75%            | 75%                     | **75%**          | —         |
| disp_rtm   | 56%            | 69%                     | **80%**          | +11건      |

- **평균 처리 시간**: 5.89초/건 (순차) → **1.02초/건 wall-clock** (병렬, 5.8× 향상) | TMDB 캐시 히트: 2% (2/100)

---

## 소스별 기여 (v8)

### cast_lead 소스 분포 (81건)
| 소스 | 건수 |
|------|-----:|
| TMDB | 51건 |
| TMDB+JW | 12건 |
| JustWatch | 9건 |
| TMDB+KMDB | 5건 |
| TMDB+DATA_GO | 2건 |
| TMDB+KMDB+DATA_GO | 1건 |
| DATA_GO | 1건 |

### rating 소스 분포 (67건)
| 소스 | 건수 |
|------|-----:|
| TMDB | 43건 |
| JustWatch | 8건 |
| TMDB+JW | 8건 |
| TMDB+KMDB | 4건 |
| TMDB+DATA_GO | 2건 |
| TMDB+KMDB+DATA_GO | 1건 |
| DATA_GO | 1건 |

### disp_rtm 소스 분포 (80건)
| 소스 | 건수 |
|------|-----:|
| TMDB | 49건 |
| TMDB+JW | 13건 |
| JustWatch | 9건 |
| TMDB+KMDB | 5건 |
| TMDB+DATA_GO | 2건 |
| TMDB+KMDB+DATA_GO | 1건 |
| DATA_GO | 1건 |

### director 소스 분포 (68건)
| 소스 | 건수 |
|------|-----:|
| TMDB | 42건 |
| TMDB+JW | 10건 |
| JustWatch | 7건 |
| TMDB+KMDB | 5건 |
| TMDB+DATA_GO | 2건 |
| TMDB+KMDB+DATA_GO | 1건 |
| DATA_GO | 1건 |

### smry 소스 분포 (84건)
| 소스 | 건수 |
|------|-----:|
| TMDB | 54건 |
| TMDB+JW | 13건 |
| JustWatch | 9건 |
| TMDB+KMDB | 5건 |
| TMDB+DATA_GO | 2건 |
| TMDB+KMDB+DATA_GO | 1건 |

### release_date / series_nm 소스 분포
| 소스 | release_date (76건) | series_nm (75건) |
|------|--------------------:|-----------------:|
| TMDB | 54건 | 54건 |
| TMDB+JW | 13건 | 13건 |
| TMDB+KMDB | 5건 | 5건 |
| TMDB+DATA_GO | 2건 | 2건 |
| TMDB+KMDB+DATA_GO | 1건 | 1건 |
| JustWatch | 1건 | — |

---

## JustWatch 기여 분석 (v8 신규, 100건)

| 컬럼 | JW 단독 | TMDB+JW (교차확인) | JW 총 기여 |
|------|--------:|------------------:|----------:|
| cast_lead | 9건 | 12건 | **21건** |
| rating | 8건 | 8건 | **16건** |
| release_date | 1건 | 13건 | **14건** |
| director | 7건 | 10건 | **17건** |
| smry | 9건 | 13건 | **22건** |
| series_nm | — | 13건 | **13건** |
| disp_rtm | 9건 | 13건 | **22건** |

- JustWatch GraphQL API: `https://apis.justwatch.com/graphql`
- 쿼리: `popularTitles(country:KR, filter:{searchQuery})` → `ageCertification` / `runtime` / `credits` / `shortDescription`
- 인증등급 매핑: ALL→전체관람가 / 7→7세이상 / 12→12세이상 / 15→15세이상 / 18→18세이상
- 유사도 임계값: 0.5 (검색 정확도 높아 완화 적용)

---

## ct_cl별 성공률 (v8)

| ct_cl | 건수 | cast | rating | date | director | smry | series | rtm |
|-------|-----:|-----:|-------:|-----:|---------:|-----:|-------:|----:|
| TV드라마 | 36 | 97% | 75% | 88% | 83% | 97% | 88% | 94% |
| TV애니메이션 | 15 | 80% | 80% | 73% | 80% | 86% | 73% | 80% |
| 영화 | 11 | 100% | 100% | 90% | 90% | 90% | 81% | 100% |
| TV 연예/오락 | 12 | 91% | 58% | 83% | 58% | 91% | 83% | 83% |
| 키즈 | 12 | 33% | 16% | 33% | 16% | 41% | 33% | 33% |
| TV 시사/교양 | 4 | 75% | 50% | 100% | 75% | 100% | 100% | 75% |
| 기타 | 3 | 66% | 100% | 100% | 66% | 100% | 100% | 100% |
| 교육/스포츠/우리동네/공연/라이프 | 5 | 20% | 20% | 0% | 0% | 20% | 0% | 20% |
| 다큐/미분류 | 2 | 100% | 100% | 100% | 100% | 100% | 100% | 100% |

---

## rating 여전히 실패 (33건)

| ct_cl | 건수 | 원인 |
|-------|-----:|------|
| TV드라마 | 9건 | 방송 전용 — JustWatch도 미매칭 케이스 잔존 |
| 키즈 | 10건 | 로컬/OTT 전용 콘텐츠, TMDB/KMDB/JW/DATA_GO 모두 미등록 |
| TV 연예/오락 | 5건 | 예능 등급 미표기 — 방심위 별도 관할 |
| TV애니메이션 | 3건 | 일부 국내 제작 미등록 |
| TV 시사/교양 | 2건 | — |
| 기타 소형 장르 | 4건 | 교육/우리동네/공연/라이프 |

---

## 핵심 인사이트

### 잘 되는 영역
- **TV드라마**: cast·smry 97%, date 88%, director 83% — TMDB+JW 커버리지 확대
- **영화**: cast·rtm 100%, rating 100% — TMDB+JustWatch 완전 보완
- **TV 연예/오락**: JustWatch 추가로 cast 67%→91%, smry 83%→91%

### 개선된 영역 (v8 vs v7)
- **disp_rtm**: JustWatch runtime 추가 → 69%→80% (+11건)
- **cast_lead**: JustWatch credits 추가 → 72%→81% (+9건)
- **director**: JustWatch credits 추가 → 57%→68% (+11건)
- **smry**: JustWatch shortDescription 추가 → 74%→84% (+10건)
- **rating**: JustWatch ageCertification 추가 → 60%→67% (+7건)

### 잔존 구조적 한계

| 문제 유형 | 건수 | 원인 |
|----------|-----:|------|
| TV 방송 프로그램 rating | ~14건 | TV 등급은 방심위 관할 — 4개 소스 모두 미보유 |
| 키즈/로컬/교육 전 필드 실패 | ~15건 | TMDB·KMDB·JW·DATA_GO 모두 미등록 |
| TV 연예/오락 director | ~5건 | 예능 감독 개념 부재 |

### 다음 개선 포인트
1. **TV 방송 rating** — 방심위(방송통신심의위원회) 방송프로그램등급 API 별도 검토
2. **키즈/로컬 콘텐츠** — 추가 데이터 소스 필요 (현재 4개 소스로도 커버 불가)
3. **JustWatch 매칭률 개선** — 유사도 임계값 조정 또는 다국어 쿼리 추가

---

## 병렬처리 성능 (v8 병렬화, 2026-03-10)

### 아키텍처

```
ThreadPoolExecutor(MAX_WORKERS=20)
  └─ process_one() ×20 동시 실행
       └─ _fetch_series_data()
            ├─ TMDB (with _sem_tmdb=8)
            ├─ [KMDB ‖ JustWatch] 내부 threading.Thread 병렬
            │    ├─ _kmdb_search() (with _sem_kmdb=3)
            │    └─ _jw_search()   (with _sem_jw=5)
            └─ DATA_GO (with _sem_data_go=3)  ← 필요 시만
```

- `SeriesCache.get_or_fetch()`: `threading.Condition` + `_CACHE_PENDING` sentinel으로 cache stampede 방지

### 처리 속도 비교

| 구분 | 100건 총 소요 | 건당 wall-clock | 160k건 예상 |
|------|-------------:|----------------:|------------:|
| v8 순차 | ~589초 (9.8분) | 5.89초 | ~267시간 |
| v8 병렬 (workers=20) | **102초 (1.7분)** | **1.02초** | **~46시간** |
| 향상 | — | — | **5.8× 빠름** |

### API별 세마포어 설정

| API | 세마포어 | 근거 |
|-----|--------:|------|
| TMDB | 8 | ~40 req/s 한도 내 여유 |
| JustWatch | 5 | 비공개 한도, 보수적 |
| KMDB | 3 | 공공 API |
| DATA_GO | 3 | 공공 API |

> MAX_WORKERS 상향(예: 30~40)으로 추가 단축 가능. TMDB rate limit 초과 시 세마포어 축소 필요.
