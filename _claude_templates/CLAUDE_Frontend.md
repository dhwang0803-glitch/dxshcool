# Frontend — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

**React/Next.js 시청자 클라이언트** — VOD 추천 목록, 유사 콘텐츠, 실시간 광고 팝업 오버레이를 제공한다.

## 파일 위치 규칙 (MANDATORY)

```
Frontend/
├── src/
│   ├── components/   ← 재사용 UI 컴포넌트 (직접 실행 X)
│   ├── pages/        ← Next.js 페이지 라우트
│   └── services/     ← API_Server 클라이언트 함수
├── public/           ← 정적 에셋 (이미지, 폰트)
└── tests/            ← Jest / Playwright
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| UI 컴포넌트 (`VideoPlayer`, `AdPopup` 등) | `src/components/` |
| 페이지 (`index.tsx`, `vod/[id].tsx` 등) | `src/pages/` |
| API 클라이언트 함수 | `src/services/api.ts` |
| WebSocket 훅 | `src/services/useAdPopup.ts` |
| 이미지, 폰트 | `public/` |
| Jest 단위 테스트 | `tests/` |

**`Frontend/` 루트 또는 프로젝트 루트에 소스 파일 직접 생성 금지.**

## 기술 스택

```typescript
// 프레임워크
Next.js 14 (App Router)
TypeScript
Tailwind CSS

// 주요 패키지
import { useWebSocket } from 'src/services/useAdPopup'  // 실시간 광고
```

## 핵심 컴포넌트

| 컴포넌트 | 역할 |
|----------|------|
| `VideoPlayer` | VOD/TV 스트림 재생 |
| `AdPopup` | 광고 팝업 오버레이 (채널이동/시청예약 버튼 포함) |
| `RecommendList` | CF_Engine 기반 개인화 추천 목록 |
| `SimilarContent` | Vector_Search 기반 유사 콘텐츠 |

## 광고 팝업 플로우

```
API_Server WebSocket /ad/popup 구독
    → 팝업 메시지 수신
    → <AdPopup> 컴포넌트 오버레이 표시
    → 사용자 액션: [채널이동] or [시청예약] or [닫기]
    → 액션 결과 API_Server에 전송 (광고 효과 측정)
```

## 인터페이스

- **업스트림**: `API_Server` — REST API (추천/유사도/VOD 상세) + WebSocket (광고 팝업)
- **다운스트림**: 시청자 브라우저/앱
