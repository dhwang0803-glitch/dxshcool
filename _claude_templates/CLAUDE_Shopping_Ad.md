# Shopping_Ad — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

사물인식 결과(detected_objects) + TV 실시간 시간표(EPG) 를 연동하여
**홈쇼핑 광고 팝업**을 생성한다.

시청자가 TV를 보는 중 화면에 보이는 상품과 유사한 홈쇼핑 상품을
팝업으로 노출하고, 채널 이동 또는 시청예약 액션을 제공한다.

## 파일 위치 규칙 (MANDATORY)

```
Shopping_Ad/
├── src/       ← import 전용 라이브러리 (직접 실행 X)
├── scripts/   ← 직접 실행 스크립트 (python scripts/xxx.py)
├── tests/     ← pytest
├── config/    ← 매핑 테이블, EPG 소스 설정 yaml
└── docs/      ← 광고 로직 설계 문서
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| EPG 파서 | `src/epg_parser.py` |
| 객체 → 상품 카테고리 매핑 | `src/product_mapper.py` |
| 팝업 메시지 빌더 | `src/popup_builder.py` |
| EPG 동기화 스크립트 | `scripts/run_epg_sync.py` |
| 광고 파이프라인 실행 | `scripts/run_ad_pipeline.py` |
| pytest | `tests/` |
| EPG 소스/매핑 설정 | `config/ad_config.yaml` |

**`Shopping_Ad/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
import requests           # EPG API 호출
import psycopg2           # detected_objects, tv_schedule 테이블 읽기
from dotenv import load_dotenv
```

## 광고 트리거 파이프라인

```
detected_objects 폴링 (새 탐지 이벤트)
    → 객체 레이블 → 상품 카테고리 매핑 (product_mapper)
    → tv_schedule 에서 현재 홈쇼핑 채널 방영 상품 조회
    → 유사도 매칭 (카테고리 일치 우선)
    → 팝업 메시지 생성 {상품명, 채널, 가격, 액션버튼}
    → API_Server /ad/popup 으로 전달
    → Frontend 팝업 오버레이 표시
```

## 팝업 메시지 스펙

```json
{
  "trigger_label": "소파",
  "product_name": "시몬스 3인용 패브릭 소파",
  "channel": "GS샵",
  "price": "299,000원",
  "actions": ["채널이동", "시청예약"]
}
```

## 인터페이스

- **업스트림**: `Object_Detection` — detected_objects 테이블
- **업스트림**: `Database_Design` — tv_schedule 테이블 (EPG 데이터)
- **다운스트림**: `API_Server` — `/ad/popup` 엔드포인트 (WebSocket or SSE)
