"""
포스터 URL → 로컬 이미지 파일 저장.
직접 실행 X — scripts/에서 import해서 사용.
"""
import os
import re
import logging
import requests

from Poster_Collection.src.base import PosterBase

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
# Windows/Linux 모두에서 파일명으로 사용 불가한 문자
_INVALID_CHARS = re.compile(r'[\\/:*?"<>|]')

_DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}


class ImageDownloader(PosterBase):
    """이미지 URL 다운로드 → 로컬 파일 저장 클래스."""

    @staticmethod
    def _safe_filename(series_id: str) -> str:
        """series_id에서 파일명으로 사용할 수 없는 문자를 '_'로 치환."""
        return _INVALID_CHARS.sub("_", str(series_id))

    @staticmethod
    def download(series_id, image_url: str, local_dir: str) -> str | None:
        """
        image_url을 다운로드해 {local_dir}/{safe_series_id}.jpg 로 저장.

        Returns:
            저장된 로컬 경로(str) or None (실패 시 — 프로세스 중단 없이 계속)
        """
        os.makedirs(local_dir, exist_ok=True)
        safe_id = ImageDownloader._safe_filename(series_id)
        dest = os.path.join(local_dir, f"{safe_id}.jpg")

        from urllib.parse import urlparse
        parsed = urlparse(image_url)
        headers = dict(_DOWNLOAD_HEADERS)
        headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

        try:
            resp = requests.get(image_url, headers=headers, timeout=10, stream=True)
            resp.raise_for_status()

            ct = resp.headers.get("Content-Type", "").split(";")[0].strip()
            if ct not in ALLOWED_CONTENT_TYPES:
                logger.warning("series_id=%s: 허용되지 않는 Content-Type=%s", series_id, ct)
                return None

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            size_kb = os.path.getsize(dest) / 1024
            logger.debug("series_id=%s 저장 완료: %s (%.1f KB)", series_id, dest, size_kb)
            return dest

        except Exception as e:
            logger.warning("series_id=%s 다운로드 실패: %s", series_id, e)
            if os.path.exists(dest):
                os.remove(dest)
            return None


# ── 싱글턴 + 하위호환 별칭 ──
_downloader = ImageDownloader()

download = ImageDownloader.download
_safe_filename = ImageDownloader._safe_filename
