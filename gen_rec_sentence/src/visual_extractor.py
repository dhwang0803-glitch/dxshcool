"""CLIP text probing으로 영상 임베딩 → 시각 키워드 추출.

원리:
    vod_embedding (CLIP ViT-B/32 영상, 512d)과
    사전 정의한 시각 묘사어의 CLIP 텍스트 임베딩(512d)을 코사인 유사도 비교.
    → top-k 키워드를 LLM 프롬프트에 주입.

사용법:
    extractor = VisualExtractor()
    keywords = extractor.extract(embedding_list, top_k=5)
    # → ["어두운 조명", "격렬한 액션", "도시 야경", ...]
"""

import logging
from functools import lru_cache

import numpy as np
import torch

log = logging.getLogger(__name__)

# 시각 묘사어 (Korean label, English CLIP query)
# 영상에서 자주 나타나는 장면/분위기/색감을 커버
_VISUAL_DESCRIPTORS = [
    # 조명·색감
    ("어두운 조명", "dark dramatic lighting"),
    ("밝고 화사한 화면", "bright vivid colorful scene"),
    ("따뜻한 색조", "warm golden hour lighting"),
    ("차갑고 푸른 색조", "cold blue toned scene"),
    ("흑백 화면", "black and white monochrome"),
    # 배경·장소
    ("도시 야경", "city night skyline"),
    ("자연 속 광활한 풍경", "vast open nature landscape"),
    ("실내 밀폐 공간", "indoor confined space"),
    ("우주·SF 배경", "outer space science fiction"),
    ("역사적 시대 배경", "historical period setting"),
    ("해변·바다", "ocean beach waves"),
    ("눈덮인 설원", "snowy winter landscape"),
    # 장면 유형
    ("격렬한 액션·전투", "intense action fight battle"),
    ("고속 추격전", "high speed chase pursuit"),
    ("폭발·불꽃", "explosion fire flames"),
    ("총격전", "gunfire shooting scene"),
    ("감동적인 포옹", "emotional embrace hug"),
    ("눈물·슬픔", "tears sadness crying"),
    ("웃음·유머", "laughter comedy humor"),
    ("긴장감 넘치는 대치", "tense standoff confrontation"),
    ("몰래 숨어드는 장면", "sneaking stealth infiltration"),
    ("마법·환상 효과", "magic fantasy visual effects"),
    ("로맨틱한 순간", "romantic intimate moment"),
    ("춤·공연", "dance performance stage"),
    ("스포츠 경기", "sports competition athletics"),
    # 인물 클로즈업
    ("강렬한 눈빛 클로즈업", "intense eye close-up portrait"),
    ("어린이·가족", "children family wholesome"),
    ("군중·집회", "crowd gathering mass"),
    ("고독한 인물", "solitary lonely figure"),
]

_DESCRIPTOR_LABELS = [d[0] for d in _VISUAL_DESCRIPTORS]
_DESCRIPTOR_QUERIES = [d[1] for d in _VISUAL_DESCRIPTORS]


class VisualExtractor:
    """CLIP text probing 기반 시각 키워드 추출기."""

    def __init__(self, model_name: str = "ViT-B/32", device: str = None):
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self._text_embeddings = None  # 지연 초기화
        self._model_name = model_name

    def _load(self):
        """CLIP 모델 로드 + 텍스트 임베딩 사전 계산 (최초 1회)."""
        if self._text_embeddings is not None:
            return
        import clip
        log.info("CLIP 모델 로드 중: %s on %s", self._model_name, self.device)
        model, _ = clip.load(self._model_name, device=self.device)
        model.eval()

        tokens = clip.tokenize(_DESCRIPTOR_QUERIES).to(self.device)
        with torch.no_grad():
            text_emb = model.encode_text(tokens).float()
            text_emb = text_emb / text_emb.norm(dim=-1, keepdim=True)

        self._text_embeddings = text_emb.cpu().numpy()  # (N, 512)
        log.info("시각 묘사어 %d개 인코딩 완료", len(_DESCRIPTOR_LABELS))

    def extract(self, embedding: list, top_k: int = 5) -> list[str]:
        """영상 임베딩 → 상위 k개 시각 키워드 반환.

        Args:
            embedding: CLIP 영상 임베딩 (512차원 float list)
            top_k: 반환할 키워드 수

        Returns:
            한국어 시각 키워드 리스트 (유사도 높은 순)
        """
        if not embedding or len(embedding) < 32:
            return []

        self._load()

        vec = np.array(embedding, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm < 1e-6:
            return []
        vec = vec / norm  # 정규화

        # 코사인 유사도 (이미 정규화된 벡터끼리 내적)
        scores = self._text_embeddings @ vec  # (N,)
        top_idx = np.argsort(scores)[::-1][:top_k]

        return [_DESCRIPTOR_LABELS[i] for i in top_idx]
