# CLIP 영상 임베딩 완료 리포트

- 작성일: 2026-03-12
- 작성자: 박아름
- 브랜치: VOD_Embedding
- 담당 태스크: tasks_A.json (TV 연예/오락 앞 절반)

---

## 배경

crawl_trailers.py로 수집한 YouTube 트레일러를 CLIP ViT-B/32 모델로 임베딩하여
각 VOD 에피소드의 512차원 영상 벡터를 생성한다.

---

## 실행 명령

```bash
# cv2 설치 (최초 1회)
pip install opencv-python

# embed_status.json 초기화 후 실행
del data\embed_status.json
cd VOD_Embedding
python scripts/batch_embed.py --output parquet --out-file data/embeddings_아름.parquet --trailers-dir data/trailers
```

---

## 실행 결과 (2026-03-12 12:11 ~ 13:48)

| 항목 | 결과 |
|------|------|
| 전체 대상 | 8,386건 |
| 성공 | **8,386건 (100%)** |
| 실패 | 0건 |
| 소요 시간 | 약 1시간 37분 |
| 출력 파일 | `data/embeddings_아름.parquet` |
| 파일 크기 | 7.8MB |

---

## 트러블슈팅

| 문제 | 원인 | 해결 |
|------|------|------|
| 전체 FAIL (No module named 'cv2') | conda 환경에 OpenCV 미설치 | `pip install opencv-python` 후 재실행 |

---

## 출력 Parquet 스펙

| 컬럼 | 타입 | 설명 |
|------|------|------|
| vod_id | str | vod.full_asset_id (vod_id_fk) |
| embedding | list[float32] | 512차원 CLIP ViT-B/32 벡터 |

### 검증 결과

| 항목 | 결과 | 상태 |
|------|------|------|
| 건수 | 8,386건 | ✅ |
| 임베딩 차원 | 512d | ✅ |
| vod_id 중복 | 0건 | ✅ |
| magnitude | 6.92 ~ 10.24 (L2 정규화 미적용) | ⚠️ 조장 확인 필요 |

> ⚠️ **정규화 미적용**: 메타 임베딩(magnitude=1.0)과 달리 raw 벡터 상태.
> ingest_to_db.py 적재 시 L2 정규화 여부를 조장과 협의 필요.

---

## 시리즈 처리 정책

- 에피소드 단위 개별 임베딩 (시리즈 그룹핑 없음)
- 같은 트레일러를 공유하는 에피소드는 동일 벡터 생성 (695개 고유 파일 → 8,386건)
- Vector_Search 단계에서 메타 임베딩(384d)과 결합 시 에피소드 차별화 보완 예정

---

## 크롤링 실패 178건 처리

- crawl_trailers.py 단계에서 YouTube 검색 결과 없음(no_result)으로 실패한 178건
- 해당 vod_id는 트레일러 파일 없음 → batch_embed.py 대상에서 자동 제외 (스킵)

---

## 다음 단계

1. ~~CLIP 영상 임베딩 → Parquet~~ ✅ 완료
2. 조장에게 `data/embeddings_아름.parquet` 전달
3. L2 정규화 여부 협의
4. `ingest_to_db.py` — Parquet → `vod_embedding` 테이블 적재 (조장 테이블 생성 후)
