"""
OCI Object Storage 업로드 라이브러리.
직접 실행 X — scripts/upload_to_oci.py에서 import해서 사용.

필수 환경변수:
    OCI_NAMESPACE   — 오브젝트 스토리지 네임스페이스
    OCI_BUCKET_NAME — 버킷 이름 (예: vod-posters)
    OCI_REGION      — 리전 (예: ap-chuncheon-1)
    OCI_CONFIG_PROFILE — OCI CLI 프로파일명 (기본: DEFAULT)

OCI CLI 설정 파일(~/.oci/config)이 사전 구성되어 있어야 함.
설치: pip install oci
"""
import logging
import os
import urllib.parse
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_client():
    import oci

    profile = os.getenv("OCI_CONFIG_PROFILE", "DEFAULT")
    config = oci.config.from_file(profile_name=profile)
    return oci.object_storage.ObjectStorageClient(config)


def build_public_url(region: str, namespace: str, bucket: str, object_name: str) -> str:
    """퍼블릭 버킷 기준 직접 접근 URL 생성. object_name은 URL 인코딩 적용."""
    encoded = urllib.parse.quote(object_name, safe="")
    return (
        f"https://objectstorage.{region}.oraclecloud.com"
        f"/n/{namespace}/b/{bucket}/o/{encoded}"
    )


def upload_file(local_path: str, object_name: str) -> str:
    """
    단일 파일을 OCI Object Storage에 업로드하고 퍼블릭 URL을 반환.

    Args:
        local_path:   로컬 이미지 파일 경로
        object_name:  버킷 내 저장될 이름 (예: '10001.jpg')

    Returns:
        퍼블릭 URL 문자열

    Raises:
        FileNotFoundError: 로컬 파일이 없을 때
        oci.exceptions.ServiceError: OCI API 오류
    """
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"파일 없음: {local_path}")

    namespace = os.getenv("OCI_NAMESPACE")
    bucket = os.getenv("OCI_BUCKET_NAME")
    region = os.getenv("OCI_REGION")

    if not all([namespace, bucket, region]):
        raise EnvironmentError(
            "OCI_NAMESPACE, OCI_BUCKET_NAME, OCI_REGION 환경변수가 필요합니다."
        )

    client = _get_client()

    with open(path, "rb") as f:
        client.put_object(
            namespace_name=namespace,
            bucket_name=bucket,
            object_name=object_name,
            put_object_body=f,
            content_type=_content_type(path.suffix),
        )

    url = build_public_url(region, namespace, bucket, object_name)
    logger.debug("업로드 완료: %s → %s", object_name, url)
    return url


def object_exists(object_name: str) -> bool:
    """버킷에 해당 오브젝트가 이미 존재하는지 확인."""
    import oci

    namespace = os.getenv("OCI_NAMESPACE")
    bucket = os.getenv("OCI_BUCKET_NAME")

    try:
        client = _get_client()
        client.head_object(
            namespace_name=namespace,
            bucket_name=bucket,
            object_name=object_name,
        )
        return True
    except oci.exceptions.ServiceError as e:
        if e.status == 404:
            return False
        raise


def _content_type(suffix: str) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix.lower(), "application/octet-stream")
