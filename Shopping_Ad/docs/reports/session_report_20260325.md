# Shopping_Ad 세션 리포트 (2026-03-25)

## 작업 내용

### Notion 개발 문서 작성 — SWDEV-033

- **대상**: Development -BackEnd 데이터베이스 (Notion)
- **문서 ID**: SWDEV-033
- **기능명**: Shopping_Ad — 제철장터/지자체 축제 광고 매칭 파이프라인
- **Notion URL**: https://www.notion.so/32e1406eba3681a3b157f0f77ed103a3

### 작성 항목 (SWDEV 템플릿 형식)

1. **기능 개요** — 모듈 역할, 목적, 범위(In/Out), 대상, 관련 문서
2. **기본 동작** — 전제조건, 트리거, 입력/처리흐름(4단계)/출력(shopping_ad_candidates.parquet 필드 테이블)
3. **예외 사항** — 입력 오류, 외부 의존성(Visit Korea/LG헬로비전 API), 데이터 불일치
4. **제약 사항** — 성능, 자원/환경, 보안, 운영(재크롤링), 호환성
5. **업스트림 & 다운스트림 의존성** — Object_Detection parquet, API, DB 테이블 수준 명시
6. **광고 서빙 플로우** — Mermaid 다이어그램 (시청자→API_Server→분기→팝업)
7. **제철장터 팝업 포맷** — 방송 중/예정 2종, 날짜 형식, 채널번호

### 처리 흐름 요약 (문서 반영 내용)

```
사전 크롤링 (1회)
  축제: crawl_festivals.py → region_festivals.yaml (63건/50지역)
  제철장터: crawl_seasonal_market.py → seasonal_market.json (10상품/21편성)

VOD 요약 집계
  build_vod_summary.py → parquet 4종 → VOD별 ad_category + primary_region

통합 매칭
  run_ad_matching.py
    관광지: primary_region → 축제 매칭 (priority=1)
    음식: Top 3 키워드 + smry 보강 → 제철장터 매칭 + 스코어링 (priority=2)

팝업 GIF 생성
  generate_all_festival_gifs.py → 63건 GIF (520x300, 테마별)
```

### 출력 필드 (문서 반영)

| 필드 | 설명 |
|------|------|
| vod_id, ad_category, ad_action_type | VOD 식별 + 광고 분류 |
| product_name, channel | 축제명/상품명, 채널(25번) |
| popup_text_live, popup_text_scheduled | 제철장터 방송 중/예정 팝업 |
| popup_title, popup_body | 축제 팝업 문구 |
| ts_start, ts_end | 광고 노출 타임스탬프 (영상 50% 이후) |
| match_score, priority | 스코어링 + 노출 우선순위 |

### 매칭 결과 (현재 기준)

- 축제 6건 (priority=1) + 제철장터 4건 (priority=2) = **10건**

## 비고

- Notion MCP 서버 연동으로 Claude Code에서 직접 작성
- Object_Detection, Shopping_Ad 브랜치 코드를 git show로 직접 확인하여 작성
- SWDEV-001 (API_Server 시스템 개요) 형식 참고
- 제철장터 재크롤링 (4/7~8) 후 데이터 업데이트 예정
