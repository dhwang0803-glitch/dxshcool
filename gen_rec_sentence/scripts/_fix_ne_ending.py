"""~네 종결 자동 치환 + 품질필터 위반 통합 → failed_edit.csv / results.parquet 업데이트."""

import pandas as pd
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

df = pd.read_parquet("gen_rec_sentence/data/colab_data/results.parquet")
df_ctx = pd.read_parquet("gen_rec_sentence/data/colab_data/vod_contexts.parquet")
ctx_map = {row["vod_id"]: row.to_dict() for _, row in df_ctx.iterrows()}

# ── 치환 규칙 (우선순위 순) ──
REPLACE_RULES = [
    # 과거형
    (r"왔네([.!]?)$", r"왔다\1"),
    (r"았네([.!]?)$", r"았다\1"),
    (r"었네([.!]?)$", r"었다\1"),
    (r"졌네([.!]?)$", r"졌다\1"),
    # 이중어미 ~다네 → ~다
    (r"다네([.!]?)$", r"다\1"),
    # ~되네 → ~된다
    (r"되네([.!]?)$", r"된다\1"),
    # ㅡ 불규칙
    (r"르네([.!]?)$", r"른다\1"),
    (r"뜨네([.!]?)$", r"뜬다\1"),
    (r"크네([.!]?)$", r"큰다\1"),
    # ㅡ 탈락 모음어간
    (r"라네([.!]?)$", r"란다\1"),
    (r"끼네([.!]?)$", r"낀다\1"),
    (r"꾸네([.!]?)$", r"꾼다\1"),
    (r"매네([.!]?)$", r"맨다\1"),
    # 모음 어간 + 네 → +ㄴ다
    (r"하네([.!]?)$", r"한다\1"),
    (r"가네([.!]?)$", r"간다\1"),
    (r"서네([.!]?)$", r"선다\1"),
    (r"나네([.!]?)$", r"난다\1"),
    (r"오네([.!]?)$", r"온다\1"),
    (r"보네([.!]?)$", r"본다\1"),
    (r"주네([.!]?)$", r"준다\1"),
    (r"치네([.!]?)$", r"친다\1"),
    (r"지네([.!]?)$", r"진다\1"),
    (r"우네([.!]?)$", r"운다\1"),
    (r"누네([.!]?)$", r"눈다\1"),
    (r"내네([.!]?)$", r"낸다\1"),
    (r"드네([.!]?)$", r"든다\1"),
    (r"이네([.!]?)$", r"인다\1"),
    (r"시네([.!]?)$", r"신다\1"),
    (r"리네([.!]?)$", r"린다\1"),
    (r"히네([.!]?)$", r"힌다\1"),
    (r"피네([.!]?)$", r"핀다\1"),
    (r"대네([.!]?)$", r"댄다\1"),
    (r"기네([.!]?)$", r"긴다\1"),
    (r"니네([.!]?)$", r"닌다\1"),
    (r"디네([.!]?)$", r"딘다\1"),
    (r"키네([.!]?)$", r"킨다\1"),
    (r"쳐네([.!]?)$", r"친다\1"),
    # 자음 어간 + 네 → +는다
    (r"잡네([.!]?)$", r"잡는다\1"),
    (r"안네([.!]?)$", r"안는다\1"),
    (r"솟네([.!]?)$", r"솟는다\1"),
    (r"딛네([.!]?)$", r"딛는다\1"),
    (r"넣네([.!]?)$", r"넣는다\1"),
    (r"않네([.!]?)$", r"않는다\1"),
    (r"있네([.!]?)$", r"있다\1"),
    (r"없네([.!]?)$", r"없다\1"),
    # 명사+네 → 명사+다
    (r"이야기네([.!]?)$", r"이야기다\1"),
    (r"드라마네([.!]?)$", r"드라마다\1"),
]

# 어색한 치환 결과 탐지
AWKWARD_ENDINGS = ["댄다", "긴다", "닌다", "딘다", "킨다"]

# false positive (실제 명사 '동네' 등)
FALSE_POSITIVE_RE = re.compile(r"(동네|[가-힣]선이네)[.!]?$")

# ── Step 1: ~네 종결 치환 ──
ne_mask = df["rec_sentence"].str.match(r".*[가-힣]네[.!]?$")
ne_indices = df[ne_mask].index.tolist()

converted = 0
awkward_idx = []
unconverted_idx = []

for idx in ne_indices:
    original = df.at[idx, "rec_sentence"]
    if FALSE_POSITIVE_RE.search(original):
        continue

    result = original
    matched = False
    for pattern, replacement in REPLACE_RULES:
        new = re.sub(pattern, replacement, result)
        if new != result:
            last_5 = new.rstrip(".!")[-5:]
            if any(awk in last_5 for awk in AWKWARD_ENDINGS):
                awkward_idx.append((idx, original, new))
            else:
                df.at[idx, "rec_sentence"] = new
                converted += 1
            matched = True
            break
    if not matched:
        unconverted_idx.append(idx)

print(f"~네 종결 총: {len(ne_indices)}건")
print(f"자동 치환 성공: {converted}건")
print(f"어색한 치환: {len(awkward_idx)}건")
print(f"치환 실패: {len(unconverted_idx)}건")
print()

# ── Step 2: 품질필터 전체 재점검 ──
_FORBIDDEN_WORDS = [
    "최고의", "역대급", "대박", "지금 바로", "놓치지 마세요", "한 번만",
    "보세요", "해보세요", "느껴보세요", "빠져보세요", "만나보세요",
    "경험하세요", "시청하세요", "확인하세요", "간직하세요", "즐겨보세요",
    "들어가볼까요", "함께해요", "기울여보세요", "선사하세요", "목격하세요",
    "경험해봐", "해봐", "들어봐", "줄거리", "내용은",
    "기대된다", "기대가 된다", "기대를 모은다",
]
_CLICHE_PATTERNS = [r"선사하", r"펼쳐지", r"불꽃"]


def check_quality(row):
    s = row["rec_sentence"]
    ctx = ctx_map.get(row["vod_id"], {})
    reasons = []
    if len(s) > 80:
        reasons.append("too_long")
    if len(s) < 20:
        reasons.append("too_short")
    for w in _FORBIDDEN_WORDS:
        if w in s:
            reasons.append(f"forbidden:{w}")
    for p in _CLICHE_PATTERNS:
        if re.search(p, s):
            reasons.append(f"cliche:{p}")
    if re.search(r"[가-힣]\s*보세요|[가-힣]\s*봐요|[가-힣]\s*봐\b", s):
        reasons.append("imperative_ending")
    if re.search(r"[가-힣]니다", s):
        reasons.append("formal_ending")
    if s.count("!") > 1:
        reasons.append("too_many_exclamation")
    if re.search(r"</?[a-zA-Z][^>]*>", s):
        reasons.append("html_tag")
    if re.search(r"[가-힣]\s+[a-z]{4,}", s):
        reasons.append("english_in_korean")
    asset_nm = str(ctx.get("asset_nm", ""))
    pure_title = re.sub(r"\s*\d+회$", "", asset_nm).strip()
    has_episode = pure_title != asset_nm.strip()
    if len(pure_title) >= 3 and pure_title in s:
        if not has_episode:
            reasons.append("title_repeat")
    ep_match = re.search(r"(\d+)회$", asset_nm)
    if ep_match and re.search(rf"\b0*{ep_match.group(1)}회", s):
        reasons.append("episode_number_repeat")
    # 치환 안 된 ~네 종결
    if re.match(r".*[가-힣]네[.!]?$", s) and not FALSE_POSITIVE_RE.search(s):
        reasons.append("ne_ending")
    return reasons


df["fail_reasons"] = df.apply(check_quality, axis=1)
df["failed"] = df["fail_reasons"].apply(lambda x: len(x) > 0)

# 어색한 치환분 → 원본 유지 + failed 마킹
for idx, orig, new in awkward_idx:
    df.at[idx, "rec_sentence"] = orig
    existing = df.at[idx, "fail_reasons"]
    existing.append("awkward_ne_conversion")
    df.at[idx, "failed"] = True

# ── Step 3: failed_edit.csv 생성 ──
failed = df[df["failed"]].copy()
failed["asset_nm"] = failed["vod_id"].map(lambda v: ctx_map.get(v, {}).get("asset_nm", ""))
failed["genre_detail"] = failed["vod_id"].map(lambda v: ctx_map.get(v, {}).get("genre_detail", ""))
failed["fail_reasons_str"] = failed["fail_reasons"].apply(lambda x: " | ".join(x))
failed["char_len"] = failed["rec_sentence"].str.len()

out = failed[["vod_id", "segment_id", "asset_nm", "genre_detail", "rec_sentence", "fail_reasons_str", "char_len"]]
out.to_csv("gen_rec_sentence/data/colab_data/failed_edit.csv", index=False, encoding="utf-8-sig")

# ── Step 4: results.parquet 저장 (치환 반영) ──
df_clean = df[["vod_id", "segment_id", "rec_sentence", "model_name"]].copy()
df_clean.to_parquet("gen_rec_sentence/data/colab_data/results.parquet", index=False)

print("=" * 60)
print(f"results.parquet 업데이트: ~네→~다 자동 치환 {converted}건 반영")
print(f"failed_edit.csv: {len(out)}건 (품질위반 + 치환실패/어색)")
print()

reason_counts = Counter()
for reasons in failed["fail_reasons"]:
    for r in reasons:
        cat = r.split(":")[0] if ":" in r else r
        reason_counts[cat] += 1
print("--- 사유별 건수 ---")
for reason, cnt in reason_counts.most_common():
    print(f"  {reason}: {cnt}건")
