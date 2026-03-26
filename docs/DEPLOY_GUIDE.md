# API Server 배포 가이드

> 최종 수정: 2026-03-26
> 대상: Cloud Run (GCP asia-northeast3)
> Service URL: https://vod-api-121620013082.asia-northeast3.run.app

---

## 브랜치 전략

```
feature branches ──PR──▶ main ──ff-only──▶ release ──▶ Cloud Run 배포
```

| 브랜치 | 역할 | 직접 커밋 |
|--------|------|----------|
| `main` | 개발 통합 | PR 머지만 |
| `release` | 배포 전용 | 절대 금지 — main에서 ff-only 머지만 |

---

## 배포 절차

### 1. feature → main 머지

```bash
# feature 브랜치에서 PR 생성 → 리뷰 → main 머지
gh pr create --base main --head <feature-branch>
```

### 2. main → release ff-only 머지

```bash
git checkout main
git pull origin main

git checkout release
git merge main --ff-only
git push origin release
```

> `--ff-only` 필수 — 머지 커밋 생성 금지. release는 항상 main의 스냅샷.

### 3. Cloud Run 배포

```bash
cd API_Server
gcloud run deploy vod-api \
  --source . \
  --region=asia-northeast3 \
  --allow-unauthenticated \
  --port=8080 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=1 \
  --max-instances=1 \
  --timeout=3600
```

### 4. 배포 확인

```bash
# Health check
curl https://vod-api-121620013082.asia-northeast3.run.app/health
# → {"status":"ok"}

# Swagger UI
# https://vod-api-121620013082.asia-northeast3.run.app/docs
```

---

## 버전 태깅

릴리스 시 release 브랜치에 annotated tag를 생성한다.

```bash
git checkout release
git tag -a v1.x.x -m "v1.x.x — 변경사항 요약"
git push origin v1.x.x
```

| 버전 | 날짜 | 주요 변경 |
|------|------|----------|
| v1.0.0 | 2026-03-26 | 최초 정식 배포 — 추천/검색/인증/시청관리/광고 전체 API |

---

## 롤백

```bash
# 이전 배포 커밋으로 release 되돌리기
git checkout release
git reset --hard <이전 배포 커밋>
git push --force origin release

# 이전 버전으로 재배포
cd API_Server
gcloud run deploy vod-api --source . --region=asia-northeast3 ...
```

또는 Cloud Run 콘솔에서 이전 리비전으로 트래픽 전환 가능.

---

## Cloud Run 설정

| 항목 | 값 | 근거 |
|------|---|------|
| 리전 | asia-northeast3 (서울) | DB와 동일 리전 |
| 메모리 | 512Mi | FastAPI + asyncpg 풀 충분 |
| CPU | 1 | 동시 10명 이하 |
| min-instances | 1 | background task 상시 실행 |
| max-instances | 1 | 인메모리 버퍼 상태 공유 불가 |
| 타임아웃 | 3600초 | WebSocket 장시간 연결 |
| 포트 | 8080 | Dockerfile CMD 기준 |

## 환경변수

Cloud Run 서비스에 설정된 변수 (Secret Manager 전환 권장):

| 변수 | 설명 |
|------|------|
| `DB_HOST` | PostgreSQL 호스트 |
| `DB_PORT` | 5432 |
| `DB_NAME` | 데이터베이스명 |
| `DB_USER` | 접속 계정 |
| `DB_PASSWORD` | 접속 비밀번호 |
| `JWT_SECRET_KEY` | JWT 서명 키 |
| `FRONTEND_URL` | CORS 허용 도메인 (미설정 시 전체 허용) |

---

## 주의사항

- release 브랜치에 직접 커밋 절대 금지
- 배포 전 main에서 `/health` 로컬 테스트 권장
- VPC 커넥터 미사용 — DB 공인 IP 직접 접속 (추후 VPC 전환 시 `--vpc-connector` 추가)
- `max-instances=1` 단일 인스턴스 — 수평 확장 시 Redis 도입 필요
