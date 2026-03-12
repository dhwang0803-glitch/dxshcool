# serving.vod_recommendation 테이블 검토 보고서

## 발견 사항

DB 확인 결과 `serving` 스키마에 `vod_recommendation` 테이블이 이미 존재함.

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

## 검토 필요 사항 (조장 확인 요청)

### 1. CF_Engine 결과 저장 위치
CF_Engine(ALS) 추천 결과를 어디에 저장할지 결정 필요.

**Option A**: 기존 `serving.vod_recommendation` 테이블 사용
- `recommendation_type` 컬럼에 CF 결과임을 나타내는 값 저장
- 사용할 값 확인 필요 (예: `'CF'`, `'ALS'`, `'COLLABORATIVE'` 등)
- 장점: 테이블 추가 불필요, 추천 결과 통합 관리
- 단점: Vector_Search 결과와 혼재

**Option B**: 별도 테이블 `cf_recommendations` 신규 생성
- CF_Engine 전용 테이블로 독립 관리
- 장점: 명확한 분리
- 단점: 테이블 추가 필요 (마이그레이션 선행)

### 2. recommendation_type 허용값 목록
현재 기본값이 `'VISUAL_SIMILARITY'`인데, CF 결과에 사용할 값이 정의되어 있는지 확인 필요.

---

## 요청 사항

- [ ] Option A / B 중 선택
- [ ] Option A 선택 시: `recommendation_type` 에 사용할 값 지정
- [ ] Option B 선택 시: 마이그레이션 실행 요청 (`20260312_create_cf_recommendations.sql`)
