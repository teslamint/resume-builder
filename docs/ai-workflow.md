# AI Workflow

Claude Code와 함께 이력서 관리 및 구직 활동을 진행하는 방법입니다.

## Claude Code Skills

이 프로젝트에는 구직 활동을 지원하는 Claude Code 스킬이 포함되어 있습니다.

### 사용 가능한 스킬

| 스킬 | 설명 | 출력 |
|------|------|------|
| `/extract-company-info` | 회사 정보 추출 | `company_info/<company>.md` |
| `/extract-job-posting` | 채용공고 추출 | `job_postings/<id>-<company>-<position>.md` |
| `/jd-screening` | JD 적합성 분석 | `jd_analysis/screening/` |
| `/extract-recruitment-info` | 채용 정보 통합 추출 | 위 두 스킬 조합 |

## 구직 워크플로우

### 1. 회사 리서치

```
/extract-company-info [회사 URL 또는 이름]
```

출력 예시:
```markdown
# 회사명

## 기본 정보
- 설립: 2020년
- 규모: 50-100명
- 산업: 핀테크

## 기술 스택
- Backend: Python, FastAPI
- Frontend: React, TypeScript
...
```

### 2. 채용공고 분석

```
/extract-job-posting [채용공고 URL]
```

지원 사이트:
- wanted.co.kr
- rememberapp.co.kr
- saramin.co.kr
- jobkorea.co.kr

### 3. 적합성 스크리닝

```
/jd-screening [채용공고 파일]
```

분석 결과:
- 필수 요건 매칭률
- 우대 사항 매칭률
- 지원 추천 여부
- 강조할 경험 포인트

## 스크리닝 기준 설정

`.claude/skills/jd-screening/SKILL.md`에서 개인 기준을 설정합니다:

```markdown
## 스크리닝 기준

### 필수 조건
- 백엔드 포지션
- 연봉 8000만원 이상
- 서울/판교 근무

### 우대 조건
- Python/FastAPI 사용
- 스타트업 환경
- 리모트 가능
```

## 이력서 맞춤화 워크플로우

### 1. 기본 이력서 생성

```bash
./build.sh job base  # 기준 이력서 생성
```

### 2. 타겟별 오버라이드 생성

```bash
mkdir -p overrides/<target>/profile
cp profile/summary-job.md overrides/<target>/profile/
# summary-job.md를 JD에 맞게 수정
```

### 3. 타겟 이력서 빌드

```bash
./build.sh job full --target <target>
```

### 4. 변경사항 확인

`build/resume-job-notes.md`에서 기본 이력서와의 차이를 확인합니다.

## 디렉토리 구조

```
resume/
├── company_info/         # 회사 정보 DB
│   └── <company>.md
├── job_postings/         # 채용공고 원본
│   └── <id>-<company>-<position>.md
├── jd_analysis/
│   ├── screening/        # 스크리닝 결과
│   │   ├── SUMMARY.md
│   │   └── <id>-<company>-<position>.md
│   └── interview/        # 면접 준비 시트
└── .claude/
    └── skills/           # Claude Code 스킬
```

## 팁

1. **스크리닝 자동화**: 여러 채용공고를 한번에 분석하여 우선순위 결정
2. **이력서 버전 관리**: Git으로 타겟별 변경사항 추적
3. **면접 준비**: 스크리닝 결과 기반으로 예상 질문 준비
