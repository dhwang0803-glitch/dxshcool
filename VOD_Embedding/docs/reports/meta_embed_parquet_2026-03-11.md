# VOD 메타데이터 임베딩 Parquet 파이프라인 개발 리포트

- 작성일: 2026-03-11
- 브랜치: VOD_Embedding

---

## 배경

- `vod_meta_embedding` 테이블이 DB에 미생성 (조장 작업 예정)
- 읽기 권한만 있어 직접 테이블 생성/적재 불가
- → 임베딩 결과를 Parquet으로 저장, 테이블 생성 후 `ingest_to_db.py`로 적재 예정

---

## 구현 파일

`VOD_Embedding/scripts/run_meta_embed_parquet.py`

---

## 임베딩 정책 (시리즈 단위 그룹핑)

| 항목 | 내용 |
|------|------|
| 모델 | paraphrase-multilingual-MiniLM-L12-v2 |
| 차원 | 384d |
| 입력 | asset_nm + ct_cl + genre + genre_detail + 감독 + 주연 + 조연 + 줄거리 + 개봉연도 |
| 그룹핑 기준 | (normalized_title, ct_cl) |
| 연산 횟수 | 166,159건 → 23,541번 (86% 절감) |
| 복사 방식 | 대표 row 1개 인코딩 → 시리즈 내 전체 row에 동일 벡터 복사 |

### 정규화 예시

| 원본 | 정규화 결과 |
|------|------------|
| 겨울왕국 [4K] | 겨울왕국 |
| 겨울왕국 (더빙) | 겨울왕국 |
| 슈퍼맨이돌아왔다 16회 | 슈퍼맨이돌아왔다 |

---

## 체크포인트 방식

- 20 시리즈마다 인코딩 즉시 Parquet + JSON 저장
- 중단 후 재시작 시 완료된 시리즈 자동 스킵
- 체크포인트 파일: `data/meta_embed_checkpoint.json`
- 출력 파일: `data/vod_meta_embedding_YYYYMMDD.parquet`

### 수정 이력

| 버전 | 내용 |
|------|------|
| v1 | 전체 인코딩 완료 후 저장 → 중단 시 전체 손실 |
| v2 | 20 시리즈 청크 단위 인코딩+저장 → 배터리/전원 차단에도 안전 |

---

## Parquet 컬럼 스펙

| 컬럼 | 타입 | 설명 |
|------|------|------|
| vod_id_fk | str | vod.full_asset_id |
| embedding | list[float] | 384차원 벡터 |
| input_text | str | 임베딩 입력 텍스트 |
| model_name | str | paraphrase-multilingual-MiniLM-L12-v2 |
| embedding_dim | int | 384 |
| vector_magnitude | float | 1.0 (L2 정규화) |
| created_at | str | ISO 8601 |

---

## 실행 방법

```bash
cd C:\Users\user\Desktop\dxshcool\VOD_Embedding
python scripts/run_meta_embed_parquet.py
```

crawl_trailers.py와 동시 실행 가능 (리소스 충돌 없음).

---

## 다음 단계

1. 파이프라인 완료 후 Parquet 파일 검증
2. 조장이 `vod_meta_embedding` 테이블 생성 확인
3. `ingest_to_db.py`로 Parquet → DB 적재
