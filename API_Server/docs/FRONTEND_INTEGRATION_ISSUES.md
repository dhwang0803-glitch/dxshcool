# API_Server × Frontend 연동 이슈 기록

> 프론트엔드 서비스 연동 이후(2026-03-23 ~) 발생한 주요 이슈 정리.
> 커밋 해시 기준 역추적 가능.

---

## 1. CORS / 배포 인프라

| 날짜 | 커밋 | 이슈 | 원인 | 해결 |
|------|------|------|------|------|
| 03-24 | `6508525` | 프론트엔드에서 API 호출 시 CORS 차단 | allow_origins 하드코딩 | `CORS_ORIGINS` 환경변수로 전환 |
| 03-28 | `e30aa6a` | 신규 프론트엔드 URL에서 CORS 차단 | dxschool-frontend URL 미등록 | 허용 origin 추가 |
| 03-28 | `b9495db` | origin/main 병합 시 CORS 설정 충돌 | 두 브랜치에서 각각 origin 추가 | 두 URL 세트 통합 |

---

## 2. 응답 스키마 불일치 (프론트엔드 크래시 유발)

| 날짜 | 커밋 | 이슈 | 원인 | 해결 |
|------|------|------|------|------|
| 03-28 | `df90abc` | `/recommend` 500 에러 | `top_vod`가 list로 변경됐으나 라우터가 단일 객체로 언패킹 | `[TopVod(**v) for v in ...]` 리스트 처리로 수정 |
| 03-28 | `5635c35` | 위 fix 누락분 | 같은 원인 재발 | 동일 패턴 2차 수정 |
| 03-28 | `ab42e49` | `/series/{id}/episodes` 404 | `series_id`에 `full_asset_id`(에피소드 ID)가 들어감 | `series_nm` 기준으로 반환하도록 수정 |
| 03-31 | `35b5937` | popular fallback에서 `series_id`에 `vod_id_fk` 혼입 | fallback 경로에서 동일 버그 미적용 | `series_nm`으로 통일 + `vod_id` 필드 추가 |
| 03-31 | `a1efc7c` | 배너 제목이 에피소드명으로 표시 | `asset_nm`(에피소드명)을 title로 사용 | `series_nm`(시리즈명) 우선 표시 |

---

## 3. 히어로 배너 품질

| 날짜 | 커밋 | 이슈 | 원인 | 해결 |
|------|------|------|------|------|
| 03-23 | `b1e7aa3` | 배너 1단 빈 결과 | `personalized_banner` 테이블 미사용 | `hybrid_recommendation` rank 1~5로 교체 |
| 03-23 | `9106805` | 개인화 배너 불안정 | 개인화 추천 커버리지 부족 | popular_recommendation top 5 공통 히어로로 확정 |
| 03-27 | `a871d33` | 테스터 계정에서 트레일러 재생 불가 VOD 노출 | `youtube_video_id` NULL인 VOD 미필터링 | 테스터 한정 youtube_id IS NOT NULL 필터 추가 |
| 03-31 | `cdcf330` | The Shining(1980) 등 오래된 콘텐츠 배너 노출 | release_date 필터 없음 | 출시 2년 이내 필터 추가 |
| 04-01 | `786ea41` | 같은 시리즈 에피소드가 히어로 배너에 중복 노출 | hybrid_recommendation이 에피소드 단위 저장 | LIMIT 30 → Python 시리즈 중복 제거 → top 10 |

---

## 4. 개인화 섹션 / 태그 배너

| 날짜 | 커밋 | 이슈 | 원인 | 해결 |
|------|------|------|------|------|
| 03-24 | `1a6a1f7` | 같은 시리즈 에피소드가 추천 배너 독점 | series_nm 중복 제거 없음 | series_nm 기준 dedup (배우 태그 + TV 연예/오락은 에피소드 단위 유지) |
| 03-26 | `08dc7f9` | 테스터 계정에서 CT_CL fallback 반복 노출 | home_service에서 테스터 격리(`_test` 테이블 분기) 누락 | `_test` 테이블 분기 적용 |
| 03-26 | `fa9b740` | 벡터 배너에 "(HD)SBS 시사교양", "채널A" 등 채널명 노출 | genre_detail 블랙리스트 미적용 | `_clean_genre_detail()` 필터 + VOD 3개 미만 배너 제외 |
| 03-26 | `91f62d1` | VOD 1~2개짜리 빈약한 배너 생성 | 최소 기준 3개로 부족 | 최소 VOD 기준 10개로 상향 |
| 03-30 | `d9002c6` | 서로 다른 태그(actor/director/genre_detail)가 하나로 합쳐짐 | 그룹핑 키가 `tag_rank`(숫자)만 사용 | `(tag_category, tag_value)` 복합 키로 수정 |
| 03-31 | `a1efc7c` | 포스터 없는 VOD가 추천에 포함 | poster_url NULL 필터 없음 | 모든 추천 쿼리에 `poster_url IS NOT NULL` 추가 |
| 03-31 | `a1efc7c` | 홈과 스마트 추천에서 cold_genre_detail 태그 중복 | 홈/추천 분리 없이 전체 노출 | 홈 rank 1~3 / 스마트 추천 rank 4~5 분리 |

---

## 5. 벡터 유사도 검색 성능

| 날짜 | 커밋 | 이슈 | 원인 | 해결 |
|------|------|------|------|------|
| 03-26 | `d250d2d` | 벡터 유사도 쿼리 느림 | 896D concat 벡터 전체 스캔 | meta_embedding 384D + IVFFlat 인덱스 2-step 쿼리로 전환 |
| 03-26 | `30d7a15` | 시리즈 중복 제거 후 10개 미달 | 버퍼 30개로 부족 | 버퍼 30 → 50 확대 |

---

## 6. 시청 데이터 / rec_sentence 매칭

| 날짜 | 커밋 | 이슈 | 원인 | 해결 |
|------|------|------|------|------|
| 03-26 | `29a1d21` | 시청내역에 기존 이력 누락 | episode_progress 1건이라도 있으면 watch_history 무시 | watch_history + episode_progress UNION 통합 |
| 03-26 | `9b88303` | UNION 후 같은 시리즈 중복 표시 | 양쪽 테이블에 동일 시리즈 존재 | ROW_NUMBER를 UNION ALL 바깥에서 계산, 시리즈당 최신 1건 |
| 03-31 | `688d702` | top_vod에 rec_sentence 미매칭 | series_nm으로 rec_sentence 조회 → 매칭 실패 | vod_id_fk 기준 JOIN으로 수정 |
| 03-31 | `d108eb8` | 위 fix 후에도 일부 에피소드 rec_sentence 누락 | 에피소드 단위 매칭이라 시리즈 내 다른 에피소드 문구 미공유 | series_nm 기반 LATERAL JOIN으로 전파 조회 |

---

## 7. 인증 / 기타

| 날짜 | 커밋 | 이슈 | 원인 | 해결 |
|------|------|------|------|------|
| 03-12 | `5d52070` | 인증 쿼리 실패 | `user_id` 컬럼으로 조회 (실제 PK는 `sha2_hash`) | sha2_hash 기준으로 수정 |
| 03-12 | `5d52070` | Windows에서 DB 연결 실패 | `DATABASE_URL` 내 `${변수}` 치환 미지원 | 개별 환경변수(`DB_HOST` 등)로 DSN 조합 fallback |
| 04-01 | `902d549` | similar_service 스키마 접두사 누락 | 테이블명에 `public.` 접두사 없음 | 스키마 접두사 추가 |

---

## 요약 통계

- **연동 기간**: 2026-03-12 ~ 2026-04-06 (약 25일)
- **총 fix 커밋**: 28건
- **가장 빈번한 이슈 유형**: 시리즈/에피소드 ID 혼동 (5건), 배너 품질 필터 부재 (5건)
- **반복 패턴**: `full_asset_id` vs `series_nm` 혼용 → 프론트 404/크래시 유발 (3회 재발)
- **교훈**: 에피소드 단위 DB 설계 ↔ 시리즈 단위 UI 표시 간 매핑 레이어 필요
