아래 명령을 한 번에 실행해서 RAG 세션 상태를 확인하고 브리핑해줘.
MEMORY.md는 system-reminder에 자동 로드됨 — 재읽기 불필요.

```bash
cd "$(git rev-parse --show-toplevel)"
git log --oneline -3
curl -s http://localhost:11434/api/tags 2>/dev/null | conda run -n myenv python -c "import sys,json; d=json.load(sys.stdin); print('Ollama RUNNING:', [m['name'] for m in d.get('models',[])])" 2>/dev/null || echo "Ollama: NOT RUNNING"
conda run -n myenv python -c "
import sys; sys.stdout.reconfigure(encoding='utf-8')
import os; from dotenv import load_dotenv; load_dotenv('.env')
import psycopg2
c=psycopg2.connect(host=os.getenv('DB_HOST'),port=os.getenv('DB_PORT'),user=os.getenv('DB_USER'),password=os.getenv('DB_PASSWORD'),dbname=os.getenv('DB_NAME'),connect_timeout=8)
cur=c.cursor()
cur.execute(\"SELECT COUNT(*) FILTER (WHERE rag_processed=TRUE), COUNT(*) FILTER (WHERE rag_processed IS NOT DISTINCT FROM FALSE), ROUND(AVG(rag_confidence) FILTER (WHERE rag_confidence IS NOT NULL)::numeric,3) FROM vod\")
r=cur.fetchone(); print(f'processed={r[0]} unprocessed={r[1]} avg_conf={r[2]}'); c.close()
" 2>/dev/null || echo "DB: 연결 실패"
```

결과를 아래 형식으로 브리핑:
```
[브랜치/커밋] RAG — <마지막 커밋 요약>
[Ollama] RUNNING (모델명) / NOT RUNNING
[RAG 현황] 완료 X건 / 미처리 X건 / 평균신뢰도 X.XXX
[다음 작업] MEMORY.md 기준 현재 Phase
[오늘 할 작업] 대기 중
```
