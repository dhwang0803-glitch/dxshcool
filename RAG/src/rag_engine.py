"""
PLAN_00b Step 3: 접근법 B — 진짜 RAG 엔진
구조: TMDB fetch → 청크 임베딩 → ChromaDB → LLM 생성

소스 변경: Wikipedia 제거 → TMDB (에피소드 시리즈 검색에 최적)
모델: jhgan/ko-sroberta-multitask (768차원)
벡터DB: ChromaDB (RAG/config/chroma_db/)
LLM: exaone3.5:7.8b (Ollama)
"""
import os
import re
import sys
import time
import hashlib
from pathlib import Path
from typing import Optional

import requests
import chromadb
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "RAG" / "config" / "api_keys.env", override=False)

CHROMA_DIR = ROOT / "RAG" / "config" / "chroma_db"

TMDB_API_KEY           = os.getenv("TMDB_API_KEY", "")
TMDB_READ_ACCESS_TOKEN = os.getenv("TMDB_READ_ACCESS_TOKEN", "")
OLLAMA_HOST            = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL           = os.getenv("OLLAMA_MODEL", "exaone3.5:7.8b")
REQUEST_TIMEOUT        = 8

_HEADERS  = {"User-Agent": "vod-rag-pipeline/1.0"}
_TMDB_URL = "https://api.themoviedb.org/3"

# 에피소드 번호 제거 패턴
_RE_EPISODE = re.compile(
    r'\s*[\(\[]?(?:\d{1,4}화|제?\d{1,4}회\.?|[Ss]\d{1,2}[Ee]\d{1,3}|'
    r'시즌\s*\d+|Season\s*\d+|\d+기|\d+편)[\)\]]?\s*\.?$',
    re.IGNORECASE,
)


def _strip_episode(title: str) -> str:
    """에피소드/회차 번호 제거: '명탐정코난 19기 59회' → '명탐정코난'"""
    prev = None
    t = title.strip()
    while t != prev:
        prev = t
        t = _RE_EPISODE.sub('', t).strip()
    return t if t else title.strip()


def _title_similarity(a: str, b: str) -> float:
    """길이 비율 패널티 적용 유사도 — 제목 불일치 방지"""
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    len_ratio = min(len(a), len(b)) / max(len(a), len(b))
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if shorter in longer:
        return len_ratio
    return len(set(a) & set(b)) / max(len(set(a)), len(set(b))) * len_ratio


def _tmdb_headers() -> dict:
    h = dict(_HEADERS)
    if TMDB_READ_ACCESS_TOKEN:
        h["Authorization"] = f"Bearer {TMDB_READ_ACCESS_TOKEN}"
    return h


def _tmdb_params(extra: dict = None) -> dict:
    p = dict(extra or {})
    if not TMDB_READ_ACCESS_TOKEN and TMDB_API_KEY:
        p["api_key"] = TMDB_API_KEY
    return p


class RAGEngine:
    CHUNK_SIZE = 200   # 자
    OVERLAP = 50       # 자

    def __init__(self):
        self._embedder = None   # lazy load
        self._client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self._collection = self._client.get_or_create_collection(
            name="vod_rag",
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def embedder(self) -> SentenceTransformer:
        if self._embedder is None:
            self._embedder = SentenceTransformer(
                "jhgan/ko-sroberta-multitask"
            )
        return self._embedder

    # ------------------------------------------------------------------
    # TMDB fetch → 구조화 텍스트 문서 생성
    # ------------------------------------------------------------------
    def _fetch_tmdb(self, title: str) -> Optional[str]:
        """TMDB에서 작품 정보를 가져와 RAG용 텍스트 문서로 변환."""
        if not (TMDB_API_KEY or TMDB_READ_ACCESS_TOKEN):
            return None

        clean = _strip_episode(title)
        spaced = re.sub(r'([가-힣A-Za-z])(\d)', r'\1 \2', clean)

        item = None
        for query in dict.fromkeys([clean, spaced, title]):
            try:
                r = requests.get(
                    f"{_TMDB_URL}/search/multi",
                    params=_tmdb_params({"query": query, "language": "ko-KR", "page": 1}),
                    headers=_tmdb_headers(),
                    timeout=REQUEST_TIMEOUT,
                )
                candidates = [
                    i for i in r.json().get("results", [])
                    if i.get("media_type") in ("movie", "tv")
                ]
                if not candidates:
                    continue
                best = max(
                    candidates,
                    key=lambda i: _title_similarity(
                        query, i.get("title") or i.get("name", "")
                    ),
                )
                if _title_similarity(query, best.get("title") or best.get("name", "")) > 0.3:
                    item = best
                    break
            except Exception:
                continue

        if not item:
            return None

        media_type = item["media_type"]
        item_id    = item["id"]

        try:
            if media_type == "movie":
                detail_url = f"{_TMDB_URL}/movie/{item_id}"
                detail = requests.get(
                    detail_url,
                    params=_tmdb_params({
                        "language": "ko-KR",
                        "append_to_response": "credits,release_dates",
                    }),
                    headers=_tmdb_headers(),
                    timeout=REQUEST_TIMEOUT,
                ).json()
            else:
                detail_url = f"{_TMDB_URL}/tv/{item_id}"
                detail = requests.get(
                    detail_url,
                    params=_tmdb_params({
                        "language": "ko-KR",
                        "append_to_response": "credits,content_ratings",
                    }),
                    headers=_tmdb_headers(),
                    timeout=REQUEST_TIMEOUT,
                ).json()
        except Exception:
            return None

        return self._build_document(detail, media_type)

    def _build_document(self, detail: dict, media_type: str) -> str:
        """TMDB 상세 응답을 RAG용 텍스트 문서로 직렬화."""
        lines = []

        # 제목
        ko_title  = detail.get("title") or detail.get("name", "")
        org_title = detail.get("original_title") or detail.get("original_name", "")
        lines.append(f"제목: {ko_title}")
        if org_title and org_title != ko_title:
            lines.append(f"원제: {org_title}")

        # 개봉일 / 첫 방영일
        if media_type == "movie":
            rd = detail.get("release_date", "")
        else:
            rd = detail.get("first_air_date", "")
        if rd:
            lines.append(f"개봉일: {rd}")

        # 장르
        genres = [g["name"] for g in detail.get("genres", [])]
        if genres:
            lines.append(f"장르: {', '.join(genres)}")

        # 줄거리
        overview = detail.get("overview", "")
        if overview:
            lines.append(f"줄거리: {overview}")

        # 감독
        credits = detail.get("credits", {})
        directors = [
            c["name"] for c in credits.get("crew", [])
            if c.get("job") == "Director"
        ]
        if not directors and media_type == "tv":
            directors = [
                c["name"] for c in credits.get("crew", [])
                if c.get("job") in ("Series Director", "Executive Producer")
            ]
        if directors:
            lines.append(f"감독: {', '.join(directors[:2])}")

        # 주연 배우 (상위 5명)
        cast = [c["name"] for c in credits.get("cast", [])[:5]]
        if cast:
            lines.append(f"주연: {', '.join(cast)}")

        # 등급 (한국 기준 우선)
        _KR_MAP = {
            "ALL": "전체이용가", "12": "12세이용가",
            "15": "15세이용가", "18": "19세이용가",
            "19": "19세이용가",
        }
        cert = ""
        if media_type == "movie":
            for entry in detail.get("release_dates", {}).get("results", []):
                if entry.get("iso_3166_1") == "KR":
                    for rd_entry in entry.get("release_dates", []):
                        cert = rd_entry.get("certification", "")
                        if cert:
                            break
                    if cert:
                        break
        else:
            for entry in detail.get("content_ratings", {}).get("results", []):
                if entry.get("iso_3166_1") == "KR":
                    cert = entry.get("rating", "")
                    break
        if cert:
            kr_cert = _KR_MAP.get(cert, cert)
            lines.append(f"등급: {kr_cert}")

        # 제작 국가
        countries = [c["name"] for c in detail.get("production_countries", [])]
        if countries:
            lines.append(f"제작국: {', '.join(countries)}")

        doc = "\n".join(lines)
        return doc if len(doc) > 50 else None

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------
    def _chunk(self, text: str) -> list[str]:
        """CHUNK_SIZE 자 단위, OVERLAP 오버랩 슬라이딩 윈도우"""
        chunks, i = [], 0
        while i < len(text):
            chunks.append(text[i: i + self.CHUNK_SIZE])
            i += self.CHUNK_SIZE - self.OVERLAP
        return [c for c in chunks if len(c.strip()) > 20]

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------
    def index_document(self, asset_nm: str, text: str) -> int:
        """TMDB 문서를 청크 분할 후 ChromaDB에 임베딩 적재. 청크 수 반환."""
        chunks = self._chunk(text)
        if not chunks:
            return 0

        prefix = hashlib.md5(asset_nm.encode()).hexdigest()[:8]
        ids = [f"{prefix}_{i}" for i in range(len(chunks))]

        existing = self._collection.get(ids=ids[:1])
        if existing["ids"]:
            return len(chunks)

        embeddings = self.embedder.encode(chunks, show_progress_bar=False).tolist()
        self._collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=[{"source": asset_nm}] * len(chunks),
        )
        return len(chunks)

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------
    def retrieve(self, query: str, k: int = 3) -> list[str]:
        """쿼리 임베딩 → 유사도 상위 k 청크 반환"""
        if self._collection.count() == 0:
            return []
        q_emb = self.embedder.encode([query], show_progress_bar=False).tolist()
        results = self._collection.query(
            query_embeddings=q_emb,
            n_results=min(k, self._collection.count()),
        )
        return results["documents"][0] if results["documents"] else []

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------
    def generate(self, asset_nm: str, context_chunks: list[str], field: str) -> Optional[str]:
        """context를 붙인 프롬프트로 exaone3.5 호출"""
        context = "\n".join(context_chunks)
        field_desc = {
            "cast_lead": "주연 배우 이름 (최대 3명, 쉼표 구분)",
            "rating": "연령 등급 (전체이용가/7세이용가/12세이용가/15세이용가/19세이용가 중 하나)",
            "release_date": "개봉일 또는 첫 방영일 (YYYY-MM-DD 형식)",
            "director": "감독 이름 (1명)",
        }.get(field, field)

        prompt = (
            f'다음은 "{asset_nm}"에 관한 정보야.\n\n'
            f"[참고 정보]\n{context}\n\n"
            f"위 정보를 바탕으로 {field_desc}만 간단히 답해줘. "
            f"정보가 없으면 '없음'이라고 답해.\n\n"
            f"{field}:"
        )
        try:
            r = requests.post(
                f"{OLLAMA_HOST}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": prompt,
                      "stream": False, "options": {"temperature": 0.1, "num_predict": 64}},
                timeout=30,
            )
            answer = r.json().get("response", "").strip()
            if not answer or answer == "없음":
                return None
            return answer
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------
    def search_with_rag(self, asset_nm: str, field: str) -> tuple[Optional[str], float]:
        """
        fetch(TMDB) → index(ChromaDB) → retrieve → generate(Ollama)
        반환: (결과값, 경과초)
        """
        t0 = time.time()

        text = self._fetch_tmdb(asset_nm)
        if not text:
            return None, time.time() - t0

        self.index_document(asset_nm, text)

        query = f"{asset_nm} {field}"
        chunks = self.retrieve(query, k=3)
        if not chunks:
            return None, time.time() - t0

        result = self.generate(asset_nm, chunks, field)
        return result, round(time.time() - t0, 2)
