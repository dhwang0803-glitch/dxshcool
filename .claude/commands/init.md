다음 단계를 순서대로 실행해서 세션을 초기화해줘.

## 1. 프로젝트 메모리 로드
`C:\Users\daewo\.claude\projects\C--Users-daewo-OneDrive----GitHub-vod-recommendation\memory\MEMORY.md` 파일을 읽고 프로젝트 현황을 파악해.

## 2. 현재 상태 확인
아래 명령들을 실행해서 현재 상태를 요약해줘.

```bash
# 브랜치 및 변경사항
git status
git log --oneline -5

# 파이프라인 상태 (파일 있을 때만)
"C:/Users/daewo/anaconda3/envs/myenv/python.exe" VOD_Embedding/pipeline/crawl_trailers.py --status 2>/dev/null
"C:/Users/daewo/anaconda3/envs/myenv/python.exe" VOD_Embedding/pipeline/batch_embed.py --status 2>/dev/null
```

## 3. 세션 규칙 적용
이번 세션에서 아래 규칙을 반드시 지켜줘.

**로그/출력 파일 읽기**
- 백그라운드 태스크 출력 파일은 절대 `cat`으로 전체를 읽지 말고, 항상 `grep`이나 `tail`로 핵심 라인만 추출
- 예: `grep -E "OK|FAIL|ERROR|완료|성공|실패" output.log | tail -20`
- yt-dlp의 `[download] X% of ...` 진행 라인은 읽지 않도록 필터링

**백그라운드 태스크 모니터링**
- 진행 확인 시: `tail -5 output.log | grep -v "download"`
- 완료 확인 시: `grep -E "\[INFO\].*완료|=== " output.log | tail -5`

**컨텍스트 관리**
- 대화가 길어지면 `/compact`를 제안해줘
- 하나의 세션에서는 파이프라인 1단계씩만 진행 (크롤링 / 임베딩 / 적재 분리)

## 4. 세션 브리핑
위 내용을 바탕으로 아래 형식으로 간결하게 브리핑해줘.

```
[현재 브랜치] ...
[마지막 커밋] ...
[파이프라인 상태] 크롤링: X건 / 임베딩: X건 / DB: X건
[오늘 할 작업] (사용자가 알려주기 전까지는 "대기 중")
```
