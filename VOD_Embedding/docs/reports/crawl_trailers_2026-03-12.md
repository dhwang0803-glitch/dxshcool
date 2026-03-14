# 트레일러 YouTube ID 매핑 크롤링 완료 리포트

- 작성일: 2026-03-12
- 작성자: 박아름
- 브랜치: VOD_Embedding
- 담당 태스크: tasks_A.json (TV 연예/오락 앞 절반)

---

## 배경

CLIP ViT-B/32 영상 임베딩을 위해 각 VOD 에피소드에 대응하는 YouTube 트레일러 영상 ID를 매핑한다.
`split_tasks.py`로 생성한 4개 분할 파일 중 `tasks_A.json`을 담당.

---

## 실행 명령

```bash
cd VOD_Embedding
python scripts/crawl_trailers.py --task-file data/tasks_A.json --trailers-dir data/trailers
```

---

## 실행 결과 (2026-03-11 ~ 2026-03-12)

| 항목 | 결과 |
|------|------|
| 전체 대상 | 9,570건 |
| 성공 | **9,392건 (98.1%)** |
| 실패 | 181건 (1.9%) |
| 실행 기간 | 2026-03-11 16:46 ~ 2026-03-12 11:56 |
| 체크포인트 파일 | `data/crawl_status.json` |

---

## 실패 분석

- **실패 원인 전체**: `no_result` — 쿼리 4종 모두 YouTube 검색 결과 없음
- **처리 방침**: 전체의 1.9% 수준으로 batch_embed.py 단계에서 스킵

### 실패 다발 시리즈 (상위 7개)

| 시리즈명 | 실패 건수 |
|---------|---------|
| 패키지로 세계일주 - 뭉쳐야 뜬다 | 27건 |
| 슈퍼맨이 돌아왔다 | 21건 |
| 뭉쳐야 찬다 | 21건 |
| 개는 훌륭하다 | 19건 |
| 신상출시 편스토랑 | 15건 |
| 세 번째 결혼 | 14건 |
| 편애중계 | 11건 |

---

## 체크포인트 방식

- 20건 처리마다 `data/crawl_status.json` 자동 저장
- 중단 후 재시작 시 완료 항목 자동 스킵

---

## 다음 단계

1. ~~트레일러 YouTube ID 매핑~~ ✅ 완료
2. `batch_embed.py` — 성공 9,392건 대상 CLIP ViT-B/32 프레임 임베딩 → `data/embeddings_아름.parquet`
3. `ingest_to_db.py` — Parquet → `vod_embedding` 테이블 적재 (조장 테이블 생성 후)
