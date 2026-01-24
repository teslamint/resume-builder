---
name: extract-job-posting
description: This skill should be used when the user asks to "extract job posting", "채용 정보 추출", "job posting extraction", "채용 공고", or provides recruitment platform URLs (wanted.co.kr, rememberapp.co.kr, saramin.co.kr, jobkorea.co.kr)
---

# 채용 정보 추출 스킬

Chrome MCP 확장을 사용하여 채용 플랫폼에서 채용 정보를 추출합니다.

## 사전 요구사항

1. Chrome MCP 확장이 설치되어 있어야 합니다
2. 채용 플랫폼에 로그인된 상태여야 합니다 (필요시)

## 추출 워크플로우

### 0. 중복 체크 (필수)

추출 전 기존 JD 파일 존재 여부 확인:

```bash
python3 templates/jd_pipeline.py --url "{URL}"
```

- 중복인 경우: 기존 파일 경로 출력, 추출 스킵
- 신규인 경우: 추출 진행

### 1. Chrome MCP 연결 확인

```
mcp__claude-in-chrome__tabs_context_mcp 호출
- createIfEmpty: true
```

### 2. URL 접근 및 페이지 로드

```
mcp__claude-in-chrome__navigate 호출
- url: [사용자 제공 URL]
- tabId: [탭 ID]
```

### 3. 플랫폼별 추출 전략

#### Wanted (wanted.co.kr)

1. `mcp__claude-in-chrome__get_page_text` 호출로 전체 텍스트 추출
2. 구조화된 텍스트에서 필요 정보 파싱

#### Remember (rememberapp.co.kr)

1. `mcp__claude-in-chrome__javascript_tool` 호출로 JavaScript 실행
2. DOM에서 직접 정보 추출:
   ```javascript
   document.querySelector('.job-title')?.innerText
   document.querySelector('.company-name')?.innerText
   ```

#### 이미지 전용 공고

1. `mcp__claude-in-chrome__computer` 호출 (action: screenshot)
2. 스크린샷 이미지에서 OCR로 텍스트 추출
3. 사용자에게 수동 입력 요청 (OCR 실패 시)

### 4. 데이터 정규화

추출된 데이터를 다음 형식으로 정규화:

```
회사명: [회사명]
포지션: [포지션]
신입/경력: [신입/경력 N년 이상 M년 이하]
근무지: [근무지]
공고 상세 내용:
[상세 내용 - 자격요건, 우대사항, 업무내용 등]
```

### 5. 파일 저장

추출된 정보를 `job_postings/` 디렉토리에 저장:
- 파일명: `{job_id}-{company}-{position}.md`
- 예: `254599-deepsearch-ai-backend-engineer.md`

## 에러 처리

### 로그인 필요

```
사용자에게 알림:
"이 페이지는 로그인이 필요합니다. 브라우저에서 로그인 후 다시 시도해주세요."
```

### 크롤링 제한

```
사용자에게 알림:
"이 플랫폼은 자동 추출을 제한합니다. 수동으로 정보를 복사해주세요."
```

### 페이지 로드 실패

```
1. 3초 대기 후 재시도
2. 실패 시 사용자에게 URL 확인 요청
```

## 지원 플랫폼

| 플랫폼 | URL 패턴 | 추출 방식 |
|--------|----------|-----------|
| Wanted | wanted.co.kr/wd/* | get_page_text |
| Remember | rememberapp.co.kr/job/* | javascript_tool |
| Saramin | saramin.co.kr/zf_user/* | get_page_text |
| JobKorea | jobkorea.co.kr/Recruit/* | get_page_text |
| 점프잇 | jumpit.saramin.co.kr/position/* | get_page_text |

## 사용 예시

사용자: "이 채용 공고 정보 추출해줘: https://www.wanted.co.kr/wd/254599"

응답:
1. Chrome MCP로 URL 접근
2. 페이지 텍스트 추출
3. 정규화된 형식으로 출력
4. job_postings/ 디렉토리에 저장
