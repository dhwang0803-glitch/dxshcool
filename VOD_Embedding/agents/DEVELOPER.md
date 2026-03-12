# Developer Agent 지시사항

## 역할
Test Writer Agent가 작성한 테스트를 통과하는 최소한의 코드를 구현한다 (TDD Green 단계).
과도한 설계나 불필요한 기능을 추가하지 않는다.

---

## 구현 원칙

1. **테스트 통과 최우선**: 현재 실패하는 테스트를 통과시키는 것만 구현한다
2. **최소 구현**: 테스트를 통과하는 가장 단순한 코드를 작성한다
3. **PLAN 준수**: 해당 Phase의 PLAN 파일 내용을 벗어나지 않는다
4. **외부 API 캐싱**: YouTube/TMDB API 호출은 반드시 캐시 레이어를 거친다 (중복 요청 방지)

---

## Phase별 구현 파일 위치

| Phase | 구현 파일 | 위치 |
|-------|----------|------|
| Phase 1 | `crawl_trailers.py` | `VOD_Embedding/pipeline/` |
| Phase 2 | `batch_embed.py` | `VOD_Embedding/pipeline/` |
| Phase 3 | `ingest_to_db.py` | `VOD_Embedding/pipeline/` |

---

## Phase 1 구현 체크리스트

### crawl_trailers.py
```
1. fetch_vod_list(): DB에서 vod_id, asset_nm, series_nm, ct_cl 조회
2. effective_series_nm(series_nm, asset_nm): 오염 series_nm 감지 → asset_nm 기반 키 반환
3. dedup_by_series_nm(): series-level 중복 제거 (SERIES_EMBED_CT_CL 적용)
4. build_search_queries(): YouTube 검색 쿼리 생성 (시리즈/에피소드 구분)
5. download_trailer(): yt-dlp 호출, crawl_status.json 갱신
6. EXCLUDE_CT_CL = {'우리동네', '미분류'}
7. SERIES_EMBED_CT_CL = {'TV드라마', 'TV 시사/교양', 'TV애니메이션', '키즈', '영화'}
8. EPISODE_EMBED_CT_CL = {'TV 연예/오락'}
9. crawl_status.json: {vod_id: {status, ct_cl, series_nm, series_key, series_nm_is_bad, asset_nm}}
```

---

## Phase 2 구현 체크리스트

### batch_embed.py
```
1. build_work_list(): crawl_status.json에서 성공한 항목만 수집
2. embed_video(path): CLIP ViT-B/32 임베딩 (512차원 float32)
3. save_pkl(results, out_file): 기본 출력 (vod_id + vector)
4. save_parquet(results, out_file): 팀원 제출용 (vod_id + embedding list)
   - 검증: dim=512, vod_id 고유, NULL 없음
5. --output {pkl,parquet} 플래그 지원
6. --out-file 플래그 지원
7. series-level: SERIES_EMBED_CT_CL은 series_key 기준 1회만 임베딩
8. episode-level: EPISODE_EMBED_CT_CL은 에피소드별 개별 임베딩
```

---

## Phase 3 구현 체크리스트

### ingest_to_db.py
```
1. load_embeddings(pkl_path): pkl 파일 로드
2. upsert_embedding(conn, vod_id, vector): ON CONFLICT DO UPDATE
3. propagate_series_embeddings(conn, crawl_status_path, dry_run):
   - series_nm_is_bad=False → WHERE series_nm = %s AND ct_cl = %s
   - series_nm_is_bad=True  → WHERE ct_cl = %s AND asset_nm LIKE %s
   - INSERT INTO vod_embedding ... SELECT ... FROM vod_embedding WHERE vod_id_fk = %s
4. --propagate 플래그 지원
5. --dry-run 플래그 지원
```

---

## DB 연결 방식

```python
from dotenv import load_dotenv
import psycopg2, os

load_dotenv('.env')  # 프로젝트 루트의 .env (VPC 접속 정보)

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD')
)
```

---

## 구현 완료 후 자가 점검

- [ ] 하드코딩된 API 키, IP, 비밀번호 없음
- [ ] os.getenv 기본값에 실제 인프라 정보 없음 (localhost/5432/postgres/"" 만 허용)
- [ ] 외부 API 호출마다 try-except + 폴백 처리
- [ ] crawl_status.json으로 중단 후 재시작 가능
- [ ] parquet 저장 시 3가지 검증 (dim=512, 고유 vod_id, NULL 없음) 통과
