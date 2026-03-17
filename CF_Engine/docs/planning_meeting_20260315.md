# CF_Engine 기획 미팅 정리 (2026-03-15)

## 현재 완성 상태
- 전체 파이프라인 구현 완료 (9/9 테스트 통과)
- parquet 생성 완료 (242,702유저 × 20개 = 4,854,040건)
- 조장에게 parquet 전달 완료

---

## 추천 방식 결정 사항

### 최종 방향: HYBRID
- CF_Engine (COLLABORATIVE) + Vector_Search (VISUAL_SIMILARITY) 점수를 가중평균
- `recommendation_type = 'HYBRID'` 로 serving.vod_recommendation 저장
- DB에 이미 HYBRID 허용값 존재 (처음부터 기획에 포함된 사항)

### 흐름
```
CF_Engine    → COLLABORATIVE 점수
Vector_Search → VISUAL_SIMILARITY 점수
        ↓
가중평균 → HYBRID 점수
        ↓
serving.vod_recommendation (HYBRID 타입)
        ↓
API_Server 서빙
```

---

## 미팅에서 확인할 사항

### 1. HYBRID 방식 확정 여부
- CF + Visual 가중치 비율 결정 (CF 몇 % + Visual 몇 %)

### 2. Vector_Search 담당
- Vector_Search 브랜치 작업 내가 담당하는지 확인
- vod_embedding 완료, user_embedding 완료 → Vector_Search 작업 가능 상태

### 3. HYBRID 계산 위치
- CF_Engine 브랜치에 HYBRID 계산 로직 추가 (별도 브랜치 불필요)
- 조장에게 제안: "CF_Engine에 HYBRID 계산까지 합치는 방향"

### 4. Top-K 개수 확정
- 현재 `top_k=20` 고정
- UI에서 몇 개 보여줄지 결정 필요

### 5. DB 적재 시점
- API_Server 연동 일정에 맞춰 언제 적재할지

---

## 스키마 이슈

### UNIQUE 제약 문제
- 현재: `UNIQUE(user_id_fk, vod_id_fk)` → 타입별 공존 불가
- HYBRID 단일 저장이면 현재 제약 그대로 유지 가능
- CF + Visual 따로 저장하는 방식이면 → `UNIQUE(user_id_fk, vod_id_fk, recommendation_type)` 변경 필요

### export_to_db.py 수정 필요 시점
- HYBRID 단일 저장: 현재 코드 그대로 사용 가능
- 타입별 분리 저장: `WHERE recommendation_type = 'COLLABORATIVE'` 조건 추가 필요

---

## Vector_Search 절차 (내가 담당 시)

```
1. vod_embedding 테이블에서 VOD 벡터 읽기
2. user_embedding 테이블에서 유저 벡터 읽기
3. 유저 벡터 ↔ VOD 벡터 코사인 유사도 계산 → Top-K 추출
4. serving.vod_recommendation에 VISUAL_SIMILARITY 타입으로 저장
```
