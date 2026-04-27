---
name: jd-screening
description: This skill should be used when the user asks to "스크리닝", "JD 스크리닝", "JD 분석", "지원 여부", "채용공고 분석", "screening analysis", or wants to evaluate a job posting against personal criteria
---

# JD 스크리닝 분석 스킬

채용공고를 사용자 정의 스크리닝 기준에 따라 분석하고 지원 여부를 판단합니다.

## 사전 요구사항

1. **스크리닝 규칙 파일** (필수)
   - 기본 경로: `private/job_postings/jd-screening-rules.md`
   - 사용자가 다른 경로 지정 가능
   - 템플릿: `example/job_postings/jd-screening-rules-template.md`
   - 예시: `example/job_postings/examples/jd-screening-rules-sample.md`

2. 분석 대상: 채용공고 파일 또는 URL

## 스크리닝 워크플로우

### 1. 입력 확인

- 채용공고 파일 경로 (예: `private/job_postings/active/*.md`)
- 채용공고 URL (Wanted, Remember 등)
- URL인 경우: `extract-job-posting` 스킬로 먼저 추출

### 2. 스크리닝 규칙 로드

```
Read: private/job_postings/jd-screening-rules.md (또는 사용자 지정 경로)
```

규칙 파일에서 추출할 정보:

- 적용 전제 (절대 조건)
- 평가 기준 목록 및 판정 조건
- 즉시 패스 키워드
- 긍정 신호 키워드
- 최종 의사결정 규칙

### 3. 기업 정보 로드 및 리스크 체크

```
private/company_info/{company}.md 파일 확인
- 회사 개요, 재무 정보, 복지 등 참고
```

**🚨 리스크 플래그 자동 체크:**

기업 정보 파일에 `⚠️ 리스크 플래그` 섹션이 있는지 확인:

```bash
# 기업 리스크 검증 (파일이 있으면)
python3 templates/jd/company_validator.py --file private/company_info/{company}.md
```

| 리스크 코드 | 스크리닝 영향 | 대응 |
|------------|--------------|------|
| TURNOVER_CRITICAL (≥50%) | 회사 안정성 **❌** 강제 | 면접 확인사항에 조직 상황 질문 추가 |
| TURNOVER_HIGH (≥30%) | 회사 안정성 **△** 권고 | "이직률 {N}%" 근거에 명시 |
| SHRINKING_FAST (순감소 >20%) | 회사 안정성 **❌** 강제 | 구조조정/사업 축소 확인 필요 |
| SALARY_LOW (상위 50% 미만) | 연봉 구조 **△** 권고 | 연봉 협상 주의사항 추가 |
| NO_INVESTMENT_DATA | 정보 부족 경고 | 스타트업 추가 검증 필요 |

> **중요**: 리스크 플래그가 critical/high면 해당 기준은 자동으로 부정 판정

**📝 데이터 불완전 경고:**

기업 정보 완성도 < 70%인 경우:

- 스크리닝 결과에 ⚠️ 경고 표시
- 누락 필드 목록 제시
- "기업 정보 보완 후 재분석 권장" 메시지

### 4. 규칙 기반 분석

규칙 파일에 정의된 각 기준에 대해 분석 수행:

| 기준 | 판정 | 근거 |
|------|------|------|
| {기준명 1} | ⭕/❌/△ | {규칙 파일 조건 기반 판정 근거} |
| {기준명 2} | ⭕/❌/△ | {규칙 파일 조건 기반 판정 근거} |
| ... | ... | ... |

> 기준 개수와 이름은 규칙 파일에 따라 달라짐

### 5. 결과 파일 저장

```
private/jd_analysis/screening/{id}-{company}-{position}.md
```

### 6. 자동 분류 (파일 이동)

스크리닝 완료 후 판정 결과에 따라 JD 파일 자동 분류:

```bash
python3 templates/jd/pipeline.py --classify <jd_file_folder>
```

| 판정 | 대상 폴더 |
|------|----------|
| 지원 추천 | `private/job_postings/conditional/high/` |
| 지원 보류 | `private/job_postings/conditional/hold/` |
| 지원 비추천 | `private/job_postings/pass/` |

## 출력 템플릿

### 출력 문체 규칙

- 스크리닝 결과는 저장용 분석 문서로 작성한다.
- 사용자에게 말을 거는 문장이나 후속 제안 문장을 쓰지 않는다.
- 금지 문구 예: `원하시면`, `해드리겠습니다`, `다음 단계로`, `~할 수 있습니다`.
- 판정은 단호하게 유지하되 회사나 포지션을 평가절하하지 않고, 후보자의 기준과 맞는지 중심으로 설명한다.
- `리드 전가 리스크`, `금융 리스크`, `즉시 컷` 같은 내부 기준 용어는 필요한 경우에만 쓰고, 근거 문장은 자연스러운 한국어로 풀어 쓴다.
- `## 핵심 근거`는 3~5개의 짧은 문단 또는 불릿으로 압축하고, 감사 로그처럼 딱딱한 표현을 피한다.

```markdown
# JD 스크리닝 분석: {회사명} - {포지션}

## 기본 정보

| 항목 | 내용 |
|------|------|
| 회사명 | {회사명} |
| 포지션 | {포지션} |
| 경력 요건 | {경력} |
| 근무지 | {근무지} |
| 공고 출처 | {URL 또는 파일 경로} |
| 분석일 | {YYYY-MM-DD} |
| 기업정보 | {✅ 완료 (N%) / ⚠️ 불완전 (N%) / ❌ 없음} |

## 🚨 기업 리스크 플래그

> 이 섹션은 company_validator.py가 감지한 리스크만 표시
> 리스크가 없으면 이 섹션 생략

| 수준 | 코드 | 내용 |
|------|------|------|
| 🚨 CRITICAL | {코드} | {메시지} |
| ⚠️ HIGH | {코드} | {메시지} |

> **영향**: {리스크가 스크리닝 판정에 미친 영향 설명}

## 스크리닝 결과

| 기준 | 판정 | 핵심 근거 |
|------|------|-----------|
| {기준명} | {⭕/❌/△} | {1줄 요약} |
| ... | ... | ... |

### 최종 판정: {지원 추천 / 지원 보류 / 지원 비추천}

## 상세 분석

### {기준명 1}

{규칙 파일 조건에 따른 상세 분석}

### {기준명 2}

{규칙 파일 조건에 따른 상세 분석}

...

## 인터뷰 확인 사항

- {면접 시 확인할 질문 1}
- {면접 시 확인할 질문 2}
- {면접 시 확인할 질문 3}

## 한 줄 요약

> {최종 판단과 핵심 이유를 한 문장으로}
```

## 규칙 파일 작성 가이드

규칙 파일은 다음 섹션을 포함해야 합니다:

### 필수 섹션

1. **적용 전제** - 기본 조건 및 커리어 방향
2. **평가 기준** - 각 기준별 판정 조건 (⭕/❌/△)
3. **즉시 패스 키워드** - 이 키워드 발견 시 ❌ 판정
4. **긍정 신호 키워드** - 이 키워드 발견 시 ⭕ 가점
5. **최종 의사결정 규칙** - 복합 조건 판정 로직

### 템플릿 및 예시

- 빈 템플릿: `example/job_postings/jd-screening-rules-template.md`
- 작성 예시: `example/job_postings/examples/jd-screening-rules-sample.md`

## 사용 예시

### 파일 기반 분석

```
사용자: "이 채용공고 스크리닝해줘: private/job_postings/active/254599-wanted.md"
```

### URL 기반 분석

```
사용자: "https://www.wanted.co.kr/wd/254599 스크리닝 분석해줘"

1. extract-job-posting 스킬로 정보 추출
2. jd-screening 규칙으로 분석
3. 결과 파일 저장
```

### 일괄 분석

```
사용자: "private/job_postings/active/ 폴더의 모든 공고 스크리닝해줘"

1. 폴더 내 모든 .md 파일 목록 조회
2. 각 파일에 대해 스크리닝 분석
3. 결과 요약 테이블 출력
```

### 커스텀 규칙 파일 사용

```
사용자: "이 공고를 my-rules.md 기준으로 스크리닝해줘"

1. my-rules.md 파일 로드
2. 해당 규칙으로 분석 수행
```
