# Phase 4 테스트 결과

**실행일**: 2026-03-08 21:30  

**환경**: VPC PostgreSQL 15.4 + pgvector 0.5.1  

**결과**: 17/17 PASS


---


## 테스트 항목별 결과


| ID | 테스트 항목 | 판정 | 실제값 | 목표 |
|-----|-----------|------|--------|------|
| E01-1 | 필수 컬럼 존재 | **PASS** | 누락=없음 | 필수 컬럼 전체 존재 |
| E01-2 | UNIQUE(vod_id_fk) 단독 제약 | **PASS** | {'uq_vod_embedding': 'UNIQUE (vod_id_fk)'} | vod_id_fk 단독 UNIQUE |
| E01-3 | CHECK 제약 존재 | **PASS** | {'chk_embedding_type', 'chk_source_type'} | chk_embedding_type, chk_source_type |
| E01-4 | 보조 인덱스 존재 | **PASS** | {'vod_embedding_pkey', 'idx_vod_emb_type', 'idx_vod_emb_updated', 'uq_vod_embedding'} | - |
| E02-1 | 적재 건수 | **PASS** | 78건 | >=78건 (파일럿) |
| E02-2 | FK 무결성 (vod 참조) | **PASS** | 고아 레코드 0건 | 0건 |
| E02-3 | 이상 벡터 | **PASS** | 0건 | 0건 |
| E02-4 | NULL 벡터 | **PASS** | 0건 | 0건 |
| E02-5 | embedding_type 분포 | **PASS** | {'VISUAL': 78} | - |
| E03-1 | 유사도 검색 cold (LIMIT 10) | **PASS** | 9.5ms | <1000ms |
| E03-2 | 유사도 검색 warm (LIMIT 10) | **PASS** | 7.6ms | <500ms |
| E04-1 | vod_recommendation 테이블 존재 | **PASS** | 기존 테이블 | - |
| E04-2 | INSERT / ON CONFLICT UPDATE | **PASS** | recommendation_id=1 | - |
| E04-3 | TTL expires_at (7일) | **PASS** | (True, True) | (True, True) |
| E04-4 | TTL 만료 삭제 쿼리 | **PASS** | 삭제 0건 | 0건 (방금 삽입한 건은 만료 안됨) |
| E05-1 | CHECK embedding_type 위반 차단 | **PASS** | CheckViolation 발생 | - |
| E05-2 | ON CONFLICT DO UPDATE 동작 | **PASS** | magnitude 8.6272 → 99.0000 | 99.0으로 업데이트 |


---


**전체**: 17/17 PASS
