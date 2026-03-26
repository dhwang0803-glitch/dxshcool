# Object_Detection 세션 리포트 (2026-03-25)

## 작업 내용

### Notion 개발 문서 작성 — SWDEV-032

- **대상**: Development -BackEnd 데이터베이스 (Notion)
- **문서 ID**: SWDEV-032
- **기능명**: Object_Detection — VOD 음식/관광지 멀티모달 인식 파이프라인
- **Notion URL**: https://www.notion.so/32e1406eba36810eb40ac5d30efe0222

### 작성 항목 (SWDEV 템플릿 형식)

1. **기능 개요** — 모듈 역할, 목적, 범위(In/Out), 대상, 관련 문서
2. **기본 동작** — 전제조건, 트리거, 입력/처리흐름(7단계)/출력(parquet 4종 테이블)
3. **예외 사항** — 입력 오류, 외부 의존성, 데이터 불일치, 권한
4. **제약 사항** — 성능, 자원/환경(로컬 전용), 보안, 운영, 호환성
5. **업스트림 & 다운스트림 의존성** — 테이블/컬럼/타입 수준 명시

### 처리 흐름 요약 (문서 반영 내용)

```
프레임 추출 (1fps)
  → YOLO 2단계 (COCO 필터 + best.pt 한식 71종)
  → CLIP zero-shot (115쿼리, multilingual)
  → Whisper STT (639키워드 매칭)
  → EasyOCR 자막 인식
  → 멀티시그널 스코어링 (10초 구간, 4종 교차검증)
  → parquet 4종 저장
```

### 산출물 테이블 (문서 반영)

| parquet | DB 테이블 | 상태 |
|---------|-----------|------|
| vod_detected_object.parquet | detected_object_yolo | DB 생성됨 |
| vod_clip_concept.parquet | detected_object_clip | DB 생성됨 |
| vod_stt_concept.parquet | detected_object_stt | DB 생성됨 |
| vod_ocr_concept.parquet | detected_object_ocr | DDL 대기 |

## 비고

- Notion MCP 서버 연동으로 Claude Code에서 직접 작성
- Object_Detection, Shopping_Ad 브랜치 코드를 git show로 직접 확인하여 작성
- SWDEV-001 (API_Server 시스템 개요) 형식 참고
