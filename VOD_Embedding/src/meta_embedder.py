"""
VOD 메타데이터 텍스트 구성 유틸리티 (import 전용)

run_meta_embed_parquet.py 에서 아래 3개 함수를 import해 사용한다.
  - build_vod_text(vod)       : VOD dict → 임베딩용 단일 텍스트
  - group_by_series(vods)     : (normalized_title, ct_cl) 기준 시리즈 그룹핑
  - pick_representative(vods) : 시리즈 내 메타데이터 완성도가 높은 대표 row 선택

⚠️  이 파일은 src/ (import 전용) — 직접 실행하지 말 것.
    DB 연결·임베딩 연산·저장 로직은 scripts/run_meta_embed_parquet.py 에 있다.
"""
import re
from collections import defaultdict
from datetime import date


# ---------------------------------------------------------------------------
# 제목 정규화
# ---------------------------------------------------------------------------

def normalize_title(title: str) -> str:
    """
    시리즈 식별을 위한 제목 정규화.
    에피소드 번호·화질·자막 표기 등을 제거해 동일 콘텐츠로 묶는다.

    예) '겨울왕국 [4K]', '겨울왕국 (더빙)', '겨울왕국 1회' → '겨울왕국'

    정규화 결과가 빈 문자열이 되면 원본 반환 (제목 자체가 괄호인 특수 케이스 방어).
    """
    if not title:
        return ''
    t = re.sub(r'[\(\[【（][^\)\]】）]*[\)\]】）]', '', title)
    t = re.sub(r'\s*\d+회\b', '', t)
    t = re.sub(r'\s*시즌\s*\d+', '', t)
    t = re.sub(r'\s*EP\d+', '', t, flags=re.IGNORECASE)
    return t.strip() or title.strip()


# ---------------------------------------------------------------------------
# 임베딩 입력 텍스트 구성
# ---------------------------------------------------------------------------

def build_vod_text(vod: dict) -> str:
    """
    VOD 메타데이터를 임베딩용 단일 텍스트로 변환.

    포함 필드: 제목 / 유형 / 장르 / 세부장르 / 감독 / 주연 / 조연 / 줄거리 / 개봉연도
    """
    parts = [
        vod.get('asset_nm') or '',
        vod.get('ct_cl') or '',
        vod.get('genre') or '',
        vod.get('genre_detail') or '',
    ]
    if vod.get('director'):
        parts.append(f"감독: {vod['director']}")
    if vod.get('cast_lead'):
        parts.append(f"주연: {vod['cast_lead']}")
    if vod.get('cast_guest'):
        parts.append(f"조연: {vod['cast_guest']}")
    if vod.get('smry'):
        parts.append(vod['smry'])
    if vod.get('release_date'):
        rd = vod['release_date']
        year = str(rd.year) if isinstance(rd, date) else str(rd)[:4]
        parts.append(year)
    return ' '.join(filter(None, parts))


# ---------------------------------------------------------------------------
# 대표 row 선택
# ---------------------------------------------------------------------------

def _completeness_score(vod: dict) -> int:
    """채워진 핵심 필드 수를 점수로 반환 (높을수록 좋음)"""
    fields = ['director', 'cast_lead', 'cast_guest', 'smry', 'release_date']
    return sum(1 for f in fields if vod.get(f))


def pick_representative(vods: list) -> dict:
    """시리즈 내 대표 row 선택: 메타데이터 완성도 기준"""
    return max(vods, key=_completeness_score)


# ---------------------------------------------------------------------------
# 시리즈 단위 그룹핑
# ---------------------------------------------------------------------------

def group_by_series(vods: list) -> dict:
    """
    (normalized_title, ct_cl) 기준으로 시리즈 그룹핑.
    asset_nm이 없는 row는 full_asset_id를 키로 사용해 단독 처리.
    반환: {(normalized_title, ct_cl): [vod, vod, ...], ...}
    """
    groups = defaultdict(list)
    for vod in vods:
        raw_title = vod.get('asset_nm')
        if raw_title and raw_title.strip():
            norm_title = normalize_title(raw_title)
        else:
            norm_title = f"__NO_TITLE__:{vod['full_asset_id']}"
        key = (norm_title, vod.get('ct_cl') or '')
        groups[key].append(vod)
    return groups
