---
name: extract-job-posting
description: This skill should be used when the user asks to "extract job posting", "채용 정보 추출", "job posting extraction", "채용 공고", or provides recruitment platform URLs (wanted.co.kr, rememberapp.co.kr, saramin.co.kr, jobkorea.co.kr)
---

# 채용 정보 추출 스킬

**HTTP 우선 + Chrome MCP fallback** 방식으로 채용 플랫폼의 JD를 추출합니다.

> **전환 정책 (2026-04-17)**: Wanted/Remember는 `templates/jd/`의 HTTP 모듈(`wanted_extract.py`, `remember_batch_extract.py`)을 직접 호출하여 15-30배 빠름 (R1 감사 실측 건당 0.5초). Saramin/Jumpit/JobKorea는 anti-bot/CSR 이슈로 Chrome MCP 유지.

## 사전 요구사항

1. **방법 A (HTTP)**: Python 3 실행 가능 환경 (표준 라이브러리만 필요)
2. **방법 B (Chrome MCP fallback)**: Chrome MCP 확장 설치 + 필요 시 로그인 상태

## 추출 워크플로우

### 0. 중복 체크 (필수)

```bash
python3 templates/jd/pipeline.py --url "{URL}"
```

- `duplicate` → 기존 파일 경로 출력, 추출 스킵
- `needs_manual` → 1단계 진행

### 1. 플랫폼 판별

URL prefix로 분기:

| 플랫폼 | URL 패턴 | 기본 경로 |
|--------|----------|-----------|
| Wanted | `wanted.co.kr/wd/{id}` | **방법 A (HTTP)** |
| Remember | `rememberapp.co.kr/job/...` 또는 `career.rememberapp.co.kr/job/...` | **방법 A (HTTP)** |
| Saramin | `saramin.co.kr/zf_user/...` | 방법 B (Chrome) |
| JobKorea | `jobkorea.co.kr/Recruit/...` | 방법 B (Chrome) |
| 점프잇 | `jumpit.saramin.co.kr/position/...` | 방법 B (Chrome) |

### 2A. 방법 A — HTTP 우선 (Wanted / Remember)

#### Wanted

```bash
python3 templates/jd/wanted_extract.py <job_id>
```

- `job_id`는 URL `wanted.co.kr/wd/{job_id}`에서 추출
- 저장 경로: `private/job_postings/unprocessed/{id}-{company_slug}-{title_slug}.md` (자동)
- stdout JSON 배열에서 첫 entry의 `status == "ok"` 확인. 아니면 → 방법 B fallback
- 회사 프로필 URL 조립: JSON의 `company.company_id` → `wanted.co.kr/company/{company_id}` (예: 311992 → 15095 → `wanted.co.kr/company/15095`)

#### Remember

```bash
echo "<url>" > /tmp/remember_url.txt
python3 templates/jd/remember_batch_extract.py /tmp/remember_url.txt
```

- 저장 경로: `private/job_postings/unprocessed/{id}-{company_slug}-{title_slug}.md` (자동)
- `private/job_postings/unprocessed/batch_results.json`에서 entry 확인 (`status == "ok"`)
- 회사 프로필 URL 조립: 규격 미확인, Phase 3(회사 정보)에서 회사명 검색 폴백 권장
- 배치 시 내부 `time.sleep(0.5)` 자동 적용

### 2B. 방법 B — Chrome MCP (Saramin / 기타, 또는 방법 A 실패 시)

1. `mcp__claude-in-chrome__tabs_context_mcp` 호출 (`createIfEmpty: true`)
2. `mcp__claude-in-chrome__navigate` (url, tabId)
3. 플랫폼별 추출:

#### Wanted (fallback 모드)

1. `mcp__claude-in-chrome__get_page_text`로 전체 텍스트 추출
2. 구조화된 텍스트에서 필요 정보 파싱

#### Remember (fallback 모드)

1. `mcp__claude-in-chrome__javascript_tool`로 DOM 직접 추출:
   ```javascript
   document.querySelector('.job-title')?.innerText
   document.querySelector('.company-name')?.innerText
   ```

#### Saramin / JobKorea / 점프잇

1. `mcp__claude-in-chrome__get_page_text`로 텍스트 추출
2. 정규표현식으로 회사명/포지션/경력/자격요건 파싱

#### 이미지 전용 공고

1. `mcp__claude-in-chrome__computer` 호출 (action: screenshot)
2. 스크린샷 OCR로 텍스트 추출
3. 실패 시 사용자 수동 입력 요청

### 3. 데이터 정규화

- **방법 A**: 마크다운 파일이 자동 생성되므로 별도 정규화 불필요
- **방법 B**: 추출된 데이터를 다음 형식으로 정규화 후 수동 저장

```
회사명: [회사명]
포지션: [포지션]
신입/경력: [신입/경력 N년 이상 M년 이하]
근무지: [근무지]
공고 상세 내용:
[상세 내용 - 자격요건, 우대사항, 업무내용 등]
```

### 4. 파일 저장

- **방법 A**: 자동 저장 (`wanted_extract.py` / `remember_batch_extract.py`)
- **방법 B**: `private/job_postings/unprocessed/{job_id}-{company}-{position}.md` 수동 생성

파일명 형식: `{job_id}-{company}-{position}.md`
예: `254599-deepsearch-ai-backend-engineer.md`

## 에러 처리

### 방법 A 실패 (`status != ok`, HTTP 404, `__NEXT_DATA__` 파싱 오류)

→ 방법 B Chrome MCP fallback 진입

### 로그인 필요 (방법 B)

```
사용자에게 알림:
"이 페이지는 로그인이 필요합니다. 브라우저에서 로그인 후 다시 시도해주세요."
```

### 크롤링 제한 (방법 B)

```
사용자에게 알림:
"이 플랫폼은 자동 추출을 제한합니다. 수동으로 정보를 복사해주세요."
```

### 페이지 로드 실패 (방법 B)

```
1. 3초 대기 후 재시도
2. 실패 시 사용자에게 URL 확인 요청
```

### Rate limit

- `wanted_extract.py`는 간격 없음 — 배치 시 호출 간 수동 `sleep 0.5` 필요
- `remember_batch_extract.py`는 내부 `time.sleep(0.5)` 자동 적용

## 지원 플랫폼

| 플랫폼 | URL 패턴 | 기본 경로 | 도구 |
|--------|----------|-----------|------|
| Wanted | wanted.co.kr/wd/* | HTTP (방법 A) | `templates/jd/wanted_extract.py` |
| Remember | rememberapp.co.kr/job/* | HTTP (방법 A) | `templates/jd/remember_batch_extract.py` |
| Saramin | saramin.co.kr/zf_user/* | Chrome MCP (방법 B) | `get_page_text` |
| JobKorea | jobkorea.co.kr/Recruit/* | Chrome MCP (방법 B) | `get_page_text` |
| 점프잇 | jumpit.saramin.co.kr/position/* | Chrome MCP (방법 B) | `get_page_text` |

## 사용 예시

사용자: "이 채용 공고 정보 추출해줘: https://www.wanted.co.kr/wd/254599"

응답 단계:
1. `python3 templates/jd/pipeline.py --url "https://www.wanted.co.kr/wd/254599"`로 중복 체크
2. 중복 아니면 `python3 templates/jd/wanted_extract.py 254599` 실행 (방법 A)
3. stdout JSON의 `status == "ok"` 확인 → 자동 저장된 마크다운 파일 경로 보고
4. status != ok 시 방법 B로 fallback
