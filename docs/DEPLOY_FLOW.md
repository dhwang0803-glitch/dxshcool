# 배포 흐름 (Cloud Run)

## 전체 흐름 요약

```
개발자 PC                    Google Cloud
──────────                   ────────────
git push
    ↓
gcloud run deploy
  --source API_Server
    ↓
소스 압축 업로드 ──────────→  GCS 버킷
                              ↓
                          Cloud Build
                          ┌─────────────────────┐
                          │ FROM python:3.12     │
                          │ pip install          │
                          │ COPY 소스코드         │
                          │ → Docker 이미지 생성   │
                          └─────────────────────┘
                              ↓
                          Artifact Registry
                          (이미지 저장소)
                              ↓
                          Cloud Run
                          ┌─────────────────────┐
                          │ 새 Revision 생성      │
                          │ 컨테이너 기동          │
                          │ uvicorn :8080 시작    │
                          │ 헬스체크 통과          │
                          │ 트래픽 100% 전환       │
                          └─────────────────────┘
                              ↓
                          https://vod-api-dev-xxx.run.app
```
