# API Server 배포 계획

> 작성일: 2026-03-23 / 최종 수정: 2026-03-31
> 대상: Cloud Run Service (GCP)
> 상태: 운영 중 (dev + prod 배포 완료)

---

## 1. 브랜치 전략

### 구조

```
feature branches ──PR──▶ main ──검증 후 FF──▶ release ──▶ Cloud Run 자동 배포
```

| 브랜치 | 역할 | 직접 커밋 |
|--------|------|----------|
| `main` | 개발 통합 (현행 유지) | feature PR 머지만 |
| `release` | 배포 전용 | 절대 금지 |

### 배포 흐름

1. feature 브랜치 → main PR 머지 (기존 워크플로우 동일)
2. main에서 충분히 검증 완료
3. release를 main으로 fast-forward 머지
4. Cloud Build가 release push 감지 → Cloud Run 자동 배포

```bash
# 배포 시점에 실행
git checkout release
git merge main --ff-only
git push origin release
```

### fast-forward 머지 규칙

- `--ff-only` 전용 — 머지 커밋 생성 금지
- release에 직접 커밋 금지 (항상 main의 특정 시점 스냅샷)
- 충돌 가능성 0 (포인터 이동만 발생)

```
main:    A ─ B ─ C ─ D ─ E ─ F
                     ↑           ↑
release:             D           F  ← ff-only로 이동
                 (이전 배포)    (신규 배포)
```

### 롤백

```bash
# 이전 배포 커밋으로 release 되돌리기
git checkout release
git reset --hard <이전 배포 커밋 해시>
git push --force origin release
# → Cloud Build가 감지하여 이전 버전으로 재배포
```

---

## 2. Cloud Build 트리거

### 트리거 조건

- 브랜치: `release`
- 경로 필터: `API_Server/**` 변경 시에만 실행
- 다른 브랜치(Database_Design, Hybrid_Layer 등) 파일 변경은 배포 트리거하지 않음

### cloudbuild.yaml

```yaml
# 프로젝트 루트에 배치
steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/$PROJECT_ID/vod-api', './API_Server']

  - name: 'gcr.io/google.appengine/exec-wrapper'
    args:
      - 'gcloud'
      - 'run'
      - 'deploy'
      - 'vod-api'
      - '--image'
      - 'gcr.io/$PROJECT_ID/vod-api'
      - '--region'
      - 'asia-northeast3'
      - '--vpc-connector'
      - 'api-connector'
      - '--allow-unauthenticated'
      - '--port'
      - '8080'
      - '--memory'
      - '512Mi'
      - '--cpu'
      - '1'
      - '--min-instances'
      - '1'
      - '--max-instances'
      - '1'
      - '--timeout'
      - '3600'
```

### 트리거 생성 명령

```bash
gcloud builds triggers create github \
  --repo-name=dxshcool \
  --branch-pattern='^release$' \
  --included-files='API_Server/**' \
  --build-config=cloudbuild.yaml
```

---

## 3. 인프라 구성

### Cloud Run 설정

| 항목 | 값 | 근거 |
|------|---|------|
| 리전 | asia-northeast3 (서울) | DB VPC와 동일 리전 |
| 메모리 | 512Mi | FastAPI + asyncpg 풀 충분 |
| CPU | 1 | 동시 10명 이하 |
| min-instances | 1 | background task(heartbeat flush, 시청예약 체커) 상시 실행 |
| max-instances | 1 | 인메모리 버퍼/WebSocket 상태 공유 불가 |
| 요청 타임아웃 | 3600초 | WebSocket `/ad/popup` 장시간 연결 |
| 포트 | 8080 | Dockerfile CMD 기준 |

### VPC 커넥터 (DB 접근용)

Cloud Run → VPC 내부 PostgreSQL 접근에 필수.

```bash
gcloud compute networks vpc-access connectors create api-connector \
  --region=asia-northeast3 \
  --network=default \
  --range=10.8.0.0/28 \
  --min-instances=2 \
  --max-instances=3 \
  --machine-type=f1-micro
```

### 환경변수

Cloud Run 서비스에 설정할 변수:

| 변수 | 설명 | 비고 |
|------|------|------|
| `DB_HOST` | PostgreSQL 내부 IP | VPC 커넥터 경유 |
| `DB_PORT` | 5432 | |
| `DB_NAME` | 데이터베이스명 | |
| `DB_USER` | 접속 계정 | |
| `DB_PASSWORD` | 접속 비밀번호 | Secret Manager 권장 |
| `JWT_SECRET_KEY` | JWT 서명 키 | Secret Manager 권장 |
| `FRONTEND_URL` | Frontend Cloud Run URL | CORS 허용 도메인 |

> 민감 변수(`DB_PASSWORD`, `JWT_SECRET_KEY`)는 GCP Secret Manager에 저장 후
> Cloud Run에서 시크릿 참조로 주입하는 것을 권장.

---

## 4. 배포 전 체크리스트

### 1회성 초기 설정 (완료)

- [x] `release` 브랜치 생성 (`main` 기준)
- [x] VPC 커넥터 생성
- [x] Cloud Build 트리거 생성
- [x] 환경변수 / Secret Manager 등록
- [x] `main.py` CORS에 Frontend URL 반영 (dev + release)

### 매 배포 시

- [ ] main에서 API_Server 동작 검증 (로컬 또는 `/health`)
- [ ] `git checkout release && git merge main --ff-only && git push origin release`
- [ ] Cloud Build 로그 확인
- [ ] `curl https://<service-url>/health` → `{"status": "ok"}`
- [ ] Swagger UI 확인 (`https://<service-url>/docs`)
- [ ] `/recommend/{user_id}` 호출 → 200 확인 (500이면 `top_vod` 언패킹 버그 의심 — `routers/recommend.py` 23번째 줄 `[TopVod(**v) for v in result["top_vod"]]` 형태인지 확인)
- [ ] Cloud Run 로그에서 `TypeError: argument after ** must be a mapping` 없는지 확인
- [ ] CORS 오류 시: 신규 프론트엔드 URL이 `main.py` `_cors_origins` 목록에 있는지 확인
- [ ] 추천 클릭 시 `/series/{id}/episodes` 404 오류 → `recommend_service.py` series_id가 `series_nm` 기준인지 확인 (`vod_id_fk` 대신 `series_nm or asset_nm` 반환해야 함)

---

## 5. 파일 구조

```
프로젝트 루트/
├── cloudbuild.yaml          ← Cloud Build 설정
└── API_Server/
    ├── Dockerfile           ← 컨테이너 빌드
    ├── requirements.txt     ← API 전용 의존성
    ├── app/
    │   ├── main.py
    │   ├── routers/
    │   ├── services/
    │   └── models/
    └── config/
        └── settings.yaml
```

---

## 6. 스케일업 전환 기준

현재 `max-instances=1` 단일 인스턴스 구성. 아래 조건 충족 시 확장 검토:

| 조건 | 현행 | 전환 시점 |
|------|------|----------|
| 동시 접속자 | ~10명 | 50명 초과 지속 |
| 인스턴스 | 1대 | 2대 이상 필요 시 Redis 도입 (세션/버퍼 공유) |
| WebSocket | 인메모리 관리 | Redis Pub/Sub 전환 |
| 시크릿 관리 | 환경변수 직접 | Secret Manager 필수 전환 |
