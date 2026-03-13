# serving.vod_recommendation 테이블 검토 보고서

## 발견 사항

DB 확인 결과 `serving` 스키마에 `vod_recommendation` 테이블이 이미 존재함.
CF_Engine 추천 결과는 이 테이블에 저장하기로 결정.

### 테이블 스키마

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `recommendation_id` | bigint | PK |
| `user_id_fk` | varchar | NOT NULL |
| `vod_id_fk` | varchar | NOT NULL |
| `rank` | smallint | NOT NULL |
| `score` | real | NOT NULL |
| `recommendation_type` | varchar | 기본값: `'VISUAL_SIMILARITY'` |
| `generated_at` | timestamptz | 기본값: now() |
| `expires_at` | timestamptz | 기본값: now() + 7일 |

---

## 조장 확인 요청

### recommendation_type 허용값 목록

CF_Engine 결과를 `serving.vod_recommendation`에 저장할 때 `recommendation_type` 컬럼에 사용할 값이 정의되어 있는지 확인 필요.

- [ ] CF_Engine 결과에 사용할 `recommendation_type` 값 지정 (예: `'CF'`, `'ALS'`, `'COLLABORATIVE'` 등)
- [ ] 허용값 목록이 있다면 공유 요청
