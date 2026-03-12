다음 단계를 순서대로 실행해서 세션을 초기화해줘.

## 1. 프로젝트 메모리 로드
`C:\Users\daewo\.claude\projects\C--Users-daewo-OneDrive----GitHub-vod-recommendation\memory\MEMORY.md` 파일을 읽고 프로젝트 현황을 파악해.

## 2. 현재 상태 확인
아래 명령들을 실행해서 현재 상태를 요약해줘.

```bash
# 브랜치 및 변경사항
git status
git log --oneline -5

# Ollama 서버 상태 확인
curl -s http://localhost:11434/api/tags 2>/dev/null | python -c "import sys,json; d=json.load(sys.stdin); print('Ollama RUNNING — 모델:', [m['name'] for m in d.get('models',[])])" 2>/dev/null || echo "Ollama NOT RUNNING"

# RAG 처리 현황 (VPC DB)
export $(grep -v '^#' .env | xargs) 2>/dev/null
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -t -c "
  SELECT
    COUNT(*) FILTER (WHERE rag_processed = TRUE) AS processed,
    COUNT(*) FILTER (WHERE rag_processed IS NOT DISTINCT FROM FALSE) AS unprocessed,
    ROUND(AVG(rag_confidence) FILTER (WHERE rag_confidence IS NOT NULL)::numeric, 3) AS avg_confidence
  FROM vod;" 2>/dev/null || echo "DB 연결 실패 또는 rag 컬럼 미존재"
```

## 3. 세션 규칙 적용
이번 세션에서 아래 규칙을 반드시 지켜줘.

**로그/출력 파일 읽기**
- 파이프라인 출력 파일은 절대 `cat`으로 전체를 읽지 말고, 항상 `grep`이나 `tail`로 핵심 라인만 추출
- 예: `grep -E "OK|FAIL|ERROR|완료|성공|실패|PASS" output.log | tail -20`
- API 검색 진행 라인(`Searching...`, `Fetching...`)은 읽지 않도록 필터링

**백그라운드 태스크 모니터링**
- 진행 확인 시: `tail -5 output.log | grep -v "Searching"`
- 완료 확인 시: `grep -E "처리 완료|PASS|FAIL|Error" output.log | tail -5`

**컨텍스트 관리**
- 대화가 길어지면 `/compact`를 제안해줘
- 하나의 세션에서는 Phase 1개씩만 진행 (파일럿 / HIGH처리 / 품질검증 분리)

**TDD 순서 준수**
- 반드시 Test Writer → Developer → Tester → Refactor → Reporter 순서로 진행
- agents/ 폴더의 각 에이전트 지시사항을 먼저 읽고 실행

## 4. 세션 브리핑
위 내용을 바탕으로 아래 형식으로 간결하게 브리핑해줘.

```
[현재 브랜치] RAG
[마지막 커밋] ...
[Ollama 상태] RUNNING (모델: ...) / NOT RUNNING
[RAG 처리 현황] 처리 완료: X건 / 미처리: X건 / 평균 신뢰도: X.XXX
[현재 Phase] Phase X — ...
[오늘 할 작업] (사용자가 알려주기 전까지는 "대기 중")
```
