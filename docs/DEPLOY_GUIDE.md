# API Server 배포 가이드

> 최종 수정: 2026-03-26
> 대상: Cloud Run (GCP asia-northeast3)

---

## Cloud Run 서비스 구조 (dev / production 분리)

| 환경 | 서비스명 | URL | 소스 브랜치 |
|------|---------|-----|-----------|
| **개발** | `vod-api-dev` | `https://vod-api-dev-121620013082.asia-northeast3.run.app` | `main` |
| **운영** | `vod-api` | `https://vod-api-121620013082.asia-northeast3.run.app` | `release` |
| **프론트 개발** | `dx-frontend` | `https://dx-frontend-121620013082.asia-northeast3.run.app` | 팀원 feature 브랜치 |
| **프론트 운영** | `dx-frontend-release` | `https://dx-frontend-release-121620013082.asia-northeast3.run.app` | Frontend release |

> **운영 서비스(`vod-api`, `dx-frontend-release`)는 고객에게 서비스 중이다.**
> 조장 승인 없이 운영 배포 절대 금지.

---

## 브랜치 전략

```
feature branches ──PR──▶ main ──▶ vod-api-dev (개발 배포)
                                       ↓
                          검증 완료 후 조장 승인
                                       ↓
                         main ──ff-only──▶ release ──▶ vod-api (운영 배포)
```

| 브랜치 | 역할 | 직접 커밋 | 배포 대상 |
|--------|------|----------|----------|
| feature | 기능 개발 | 자유 | 없음 |
| `main` | 개발 통합 | PR 머지만 | `vod-api-dev` |
| `release` | 운영 전용 | **절대 금지** — 조장이 main에서 ff-only 머지만 | `vod-api` |

---

## 개발 배포 절차 (vod-api-dev)

팀원이 기능 테스트를 요청하거나 dev 서버 업데이트가 필요할 때 사용한다.

### 1. feature → main 머지

```bash
# feature 브랜치에서 PR 생성 → 리뷰 → main 머지
gh pr create --base main --head <feature-branch>
gh pr merge <PR번호> --merge
```

### 2. main → vod-api-dev 배포

```bash
git checkout main
git pull origin main

cd API_Server
gcloud run deploy vod-api-dev \
  --source . \
  --region=asia-northeast3 \
  --allow-unauthenticated \
  --port=8080 \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --timeout=3600
```

### 3. 배포 확인

```bash
curl https://vod-api-dev-121620013082.asia-northeast3.run.app/health
# → {"status":"ok"}

# Swagger UI
# https://vod-api-dev-121620013082.asia-northeast3.run.app/docs
```

### 4. CORS 환경변수 (프론트엔드 origin 추가 시)

```bash
# 쉼표 포함 값은 ^||^ 구분자 사용
gcloud run services update vod-api-dev \
  --region=asia-northeast3 \
  --update-env-vars='^||^CORS_ORIGINS=https://dx-frontend-121620013082.asia-northeast3.run.app,http://localhost:3000'
```

---

## 운영 배포 절차 (vod-api) — 조장 전용

> **운영 배포는 dev 검증 완료 + 조장 승인 후에만 진행한다.**
> release 브랜치를 직접 건드리거나 vod-api에 임의 배포하지 않는다.

### 1. dev 서버에서 검증 완료 확인

- [ ] `vod-api-dev` health check 정상
- [ ] 주요 엔드포인트 수동 테스트 완료
- [ ] 프론트엔드 연동 테스트 완료
- [ ] 조장 승인

### 2. main → release ff-only 머지

```bash
git checkout main
git pull origin main

git checkout release
git merge main --ff-only    # ff-only 필수 — 머지 커밋 금지
git push origin release
```

> `--ff-only` 실패 시: release에 직접 커밋이 있다는 뜻. 절대로 force merge하지 말고 원인 파악 후 조장에게 보고.

### 3. release → vod-api 배포

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

### 4. 배포 확인 + 버전 태깅

```bash
curl https://vod-api-121620013082.asia-northeast3.run.app/health
# → {"status":"ok"}

git checkout release
git tag -a v1.x.x -m "v1.x.x — 변경사항 요약"
git push origin v1.x.x
```

---

## Cloud Run 설정 비교

| 항목 | vod-api-dev (개발) | vod-api (운영) |
|------|-------------------|---------------|
| min-instances | 0 (비용 절감) | 1 (상시 가동) |
| max-instances | 3 | 1 (인메모리 상태 공유 불가) |
| 메모리 | 512Mi | 512Mi |
| CPU | 1 | 1 |
| 타임아웃 | 3600초 | 3600초 |
| 포트 | 8080 | 8080 |

## 환경변수

Cloud Run 서비스에 설정된 변수 (Secret Manager 전환 권장):

| 변수 | 설명 | dev/prod 동일 |
|------|------|--------------|
| `DB_HOST` | PostgreSQL 호스트 | O |
| `DB_PORT` | 5432 | O |
| `DB_NAME` | 데이터베이스명 | O |
| `DB_USER` | 접속 계정 | O |
| `DB_PASSWORD` | 접속 비밀번호 | O |
| `JWT_SECRET_KEY` | JWT 서명 키 | O |
| `CORS_ORIGINS` | CORS 허용 도메인 (쉼표 구분) | X (각각 설정) |

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

## 버전 이력

| 버전 | 날짜 | 주요 변경 |
|------|------|----------|
| v1.0.0 | 2026-03-26 | 최초 정식 배포 — 추천/검색/인증/시청관리/광고 전체 API |

---

## 주의사항

- **release 브랜치 직접 커밋·머지 절대 금지** — 조장 승인 후 ff-only만
- **"배포해줘" 요청 = dev 배포(`vod-api-dev`)가 기본** — 운영은 명시적 요청 시에만
- 배포 전 main에서 `/health` 로컬 테스트 권장
- VPC 커넥터 미사용 — DB 공인 IP 직접 접속 (추후 VPC 전환 시 `--vpc-connector` 추가)
- 운영 `max-instances=1` 단일 인스턴스 — 수평 확장 시 Redis 도입 필요
