> ⚠️ **[DEPRECATED — 2026-03-11]**
> 벡터 저장소를 **pgvector 단일화**로 결정 (2026-03-08). Milvus 미사용.
> 이 문서는 의사결정 히스토리 보존 목적으로만 유지됩니다. 참조 또는 실행 금지.

---

# Milvus VPC 설치 가이드 (Standalone)

**작성일**: 2026-03-08
**환경**: VPC Ubuntu 20.04+ / Docker + Docker Compose
**버전**: Milvus 2.4.x (Standalone)
**소요 시간**: 약 15~30분

---

## 1. 사전 조건 확인

```bash
# Docker 버전 확인 (20.10.0 이상 필요)
docker --version

# Docker Compose 버전 확인 (2.0.0 이상 필요)
docker compose version

# 메모리 확인 (최소 4GB 권장, 현재 VPC 4GB)
free -h

# 디스크 여유 공간 확인 (최소 10GB 권장)
df -h /
```

Docker가 없으면 먼저 설치:
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

---

## 2. Milvus Standalone 설치

### 2-1. docker-compose.yml 다운로드

```bash
mkdir -p ~/milvus && cd ~/milvus

# Milvus 공식 standalone docker-compose 파일 다운로드
wget https://github.com/milvus-io/milvus/releases/download/v2.4.17/milvus-standalone-docker-compose.yml \
     -O docker-compose.yml
```

### 2-2. 포트 및 볼륨 확인

```bash
cat docker-compose.yml
```

기본 포트:
| 포트 | 용도 |
|------|------|
| `19530` | gRPC API (pymilvus 연결) |
| `9091` | REST API / Health check |
| `2379` | etcd (내부용, 외부 노출 불필요) |
| `9000` | MinIO (내부용, 외부 노출 불필요) |

### 2-3. 실행

```bash
cd ~/milvus

# 백그라운드 실행
docker compose up -d

# 컨테이너 상태 확인 (3개 컨테이너: milvus-standalone, milvus-etcd, milvus-minio)
docker compose ps
```

정상 실행 시 출력:
```
NAME                    STATUS          PORTS
milvus-etcd             Up (healthy)    ...
milvus-minio            Up (healthy)    ...
milvus-standalone       Up (healthy)    0.0.0.0:19530->19530/tcp, 0.0.0.0:9091->9091/tcp
```

### 2-4. Health Check

```bash
# REST API로 상태 확인
curl http://localhost:9091/healthz
# 기대 응답: {"status":"ok"}

# 로그 확인 (이상 없으면 'proxy' 관련 로그가 정상 출력됨)
docker compose logs --tail=20 milvus-standalone
```

---

## 3. VPC 방화벽 설정

**19530 포트**를 로컬 Python 클라이언트가 접근할 수 있도록 허용:

```bash
# UFW (Ubuntu 기본 방화벽)
sudo ufw allow 19530/tcp
sudo ufw status

# 또는 특정 IP만 허용 (보안 강화)
sudo ufw allow from <로컬_IP> to any port 19530
```

> VPC 보안 그룹(Security Group)을 사용하는 경우, 콘솔에서 인바운드 규칙에 TCP 19530 추가 필요.

---

## 4. pymilvus 설치 (로컬 Python 환경)

```bash
# myenv conda 환경에서 설치
conda activate myenv
pip install pymilvus==2.4.9
```

---

## 5. 연결 테스트

```python
# test_milvus_connection.py
from pymilvus import MilvusClient

client = MilvusClient(uri="http://<VPC_IP>:19530")

# 서버 버전 확인
print("Milvus 연결 성공:", client.get_server_version())

# 컬렉션 목록 확인
print("컬렉션 목록:", client.list_collections())
```

```bash
python test_milvus_connection.py
# 기대 출력: Milvus 연결 성공: v2.4.x
```

---

## 6. .env 파일 설정 추가

기존 `.env` 파일에 Milvus 접속 정보 추가:

```env
# PostgreSQL (기존)
DB_HOST=<VPC_IP>
DB_PORT=5432
DB_NAME=vod_db
DB_USER=<username>
DB_PASSWORD=<password>

# Milvus (신규 추가)
MILVUS_HOST=<VPC_IP>
MILVUS_PORT=19530
```

---

## 7. VOD 파이프라인 실행

Milvus 설치 완료 후 `vod_ingest_pipeline.py` 실행:

```bash
conda activate myenv
cd Database_Design/migration

# pkl 파일로 실행 (이미 임베딩된 경우)
python vod_ingest_pipeline.py --pkl C:/Users/daewo/DX_prod_2nd/video_embs.pkl

# trailers 폴더로 실행 (임베딩부터 새로 실행)
python vod_ingest_pipeline.py --trailers-dir C:/Users/daewo/DX_prod_2nd/trailers

# DRY-RUN (DB 변경 없이 결과 미리 확인)
python vod_ingest_pipeline.py --trailers-dir C:/Users/daewo/DX_prod_2nd/trailers --dry-run

# Milvus 없이 PostgreSQL만 삽입 (Milvus 설치 전 테스트)
python vod_ingest_pipeline.py --trailers-dir ./trailers --no-milvus --dry-run
```

---

## 8. Milvus 컬렉션 확인

삽입 후 검증:

```python
from pymilvus import MilvusClient

client = MilvusClient(uri="http://<VPC_IP>:19530")

# 컬렉션 정보
info = client.describe_collection("vod_visual_embeddings")
print(info)

# 저장된 엔티티 수
stats = client.get_collection_stats("vod_visual_embeddings")
print("벡터 수:", stats["row_count"])

# 유사도 검색 테스트 (임의 쿼리 벡터)
import numpy as np
query_vector = np.random.rand(512).tolist()
results = client.search(
    collection_name="vod_visual_embeddings",
    data=[query_vector],
    limit=3,
    output_fields=["vod_id"],
)
print("검색 결과:", results)
```

---

## 9. 운영 관리

### 재시작

```bash
cd ~/milvus
docker compose restart
```

### 자동 시작 설정 (서버 재부팅 후 자동 실행)

```bash
# docker-compose.yml에 restart: always 확인 (기본 설정됨)
grep "restart" docker-compose.yml
```

### 데이터 백업

Milvus 데이터는 `~/milvus/volumes/` 디렉토리에 저장됨:

```bash
# 볼륨 위치 확인
docker inspect milvus-standalone | grep -A 5 "Mounts"

# 백업 (단순 복사)
cp -r ~/milvus/volumes ~/milvus/volumes_backup_$(date +%Y%m%d)
```

### 중지 및 삭제

```bash
# 중지 (데이터 보존)
docker compose down

# 완전 삭제 (데이터 포함)
docker compose down -v
```

---

## 10. 문제 해결

| 증상 | 원인 | 해결 |
|------|------|------|
| `Connection refused 19530` | 방화벽 차단 | `ufw allow 19530/tcp` |
| `milvus-standalone` 컨테이너 unhealthy | 메모리 부족 | 다른 서비스 종료 후 재시작 |
| `etcd` 연결 실패 | etcd 컨테이너 미시작 | `docker compose up -d` 재실행 |
| 벡터 삽입 후 검색 결과 없음 | 인덱스 미로드 | `client.load_collection("vod_visual_embeddings")` 실행 |

---

**다음 단계**: `Database_Design/plans/PLAN_04_EXTENSION_TABLES.md`
**파이프라인**: `Database_Design/migration/vod_ingest_pipeline.py`
