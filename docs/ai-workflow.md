# AI Workflow

Claude Code와 함께 이력서 관리 및 구직 활동을 진행하는 방법입니다.

## Claude Code Skills

이 프로젝트에는 구직 활동을 지원하는 Claude Code 스킬이 포함되어 있습니다.

### 사용 가능한 스킬

| 스킬 | 설명 | 출력 |
|------|------|------|
| `/extract-company-info` | 회사 정보 추출 | `private/company_info/<company>.md` |
| `/extract-job-posting` | 채용공고 추출 | `private/job_postings/<id>-<company>-<position>.md` |
| `/jd-screening` | JD 적합성 분석 | `private/jd_analysis/screening/` |
| `/jd-batch` | 여러 채용공고 배치 처리 및 재분류 | `private/job_postings/` 자동 분류 |
| `/extract-recruitment-info` | 채용 정보 통합 추출 | 위 두 스킬 조합 |

## 구직 워크플로우

### 0. 자동 파이프라인 (권장)

`templates/jd/auto.py`로 URL 수집부터 분류까지 한 번에 수행할 수 있습니다.

```bash
# 전체 자동화 (검색 → JD 추출 → 회사정보 → 스크리닝 → 분류)
python3 templates/jd/auto.py

# 검색 없이 URL 파일로 실행
python3 templates/jd/auto.py --from-urls private/job_postings/unprocessed/search_YYYYMMDD_HHMM.txt

# 기존 JD만 스크리닝/분류
python3 templates/jd/auto.py --screening-only --from-urls private/job_postings/unprocessed/search_YYYYMMDD_HHMM.txt
```

TheVC 처리 옵션:

```bash
# 기본: 투자정보 추출 실패(로그인 필요 포함) 시 해당 항목 계속 진행
python3 templates/jd/auto.py --thevc-mode auto

# TheVC 투자정보가 반드시 필요할 때
python3 templates/jd/auto.py --thevc-mode require

# 로그인 후 보완 큐 재처리
python3 templates/jd/auto.py --company-enrichment-only --thevc-mode require
```

추가 옵션:

```bash
# 기존 회사정보 completeness가 60% 미만이면 재수집
python3 templates/jd/auto.py --min-completeness 60

# 검색 스크립트
python3 templates/jd/search.py --query "백엔드 시니어" --dry-run
python3 templates/jd/search.py --status
```

#### `--min-completeness N`

기존 `private/company_info/` 파일의 completeness 점수가 N% 미만일 때만 회사 정보를 재수집합니다 (0~100, 기본값 0).
TheVC 보완 큐 재처리(`--company-enrichment-only`)와 함께 사용하면, 이미 충분한 정보가 있는 회사는 건너뛰고 부족한 회사만 보강합니다.

#### 헤드헌팅 회사 자동 감지

회사명에 헤드헌팅 키워드(써치, 서치펌, 헤드헌팅, 리크루팅, 인력파견, 헤드헌터)가 포함되면 자동으로 감지하여 회사 정보 수집을 건너뜁니다. 최소한의 stub 파일만 생성되며, completeness는 0으로 설정됩니다.

#### 중복 JD 검색 범위

`find_existing_jd()`는 다음 디렉토리를 모두 검색하여 중복을 확인합니다:
- `private/job_postings/` (루트)
- `private/job_postings/pass/`
- `private/job_postings/conditional/` 및 하위: `high/`, `hold/`, `middle/`, `low/`
- `private/job_postings/applied/`, `rejected/`
- `private/job_postings/high_priority/`, `on_going/`

출력 파일:
- 실행 결과: `private/job_postings/auto_results/auto_<run_id>.json`
- TheVC 보완 큐: `private/job_postings/unprocessed/company_enrichment_thevc.txt`

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

참고:
- 자동 파이프라인의 스크리닝은 LLM 호출(Claude CLI 우선, 실패 시 Codex CLI fallback)로 수행됩니다.
- LLM 실패 시 기본 판정은 `지원 보류`로 처리됩니다.

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
mkdir -p private/overrides/<target>/profile
cp private/profile/summary-job.md private/overrides/<target>/profile/
# summary-job.md를 JD에 맞게 수정
```

### 3. 타겟 이력서 빌드

```bash
./build.sh job full --target <target>
```

### 4. 변경사항 확인

`private/build/resume-job-notes.md`에서 기본 이력서와의 차이를 확인합니다.

## 디렉토리 구조

```
resume/
├── private/              # 개인 데이터 (gitignored)
│   ├── company_info/     # 회사 정보 DB
│   │   └── <company>.md
│   ├── job_postings/     # 채용공고 원본
│   │   └── <id>-<company>-<position>.md
│   └── jd_analysis/
│       └── screening/    # 스크리닝 결과
│           ├── SUMMARY.md
│           └── <id>-<company>-<position>.md
├── example/
│   └── interview/        # 면접 준비 시트 예제
└── .claude/
    └── skills/           # Claude Code 스킬
```

## 팁

1. **스크리닝 자동화**: 여러 채용공고를 한번에 분석하여 우선순위 결정
2. **이력서 버전 관리**: Git으로 타겟별 변경사항 추적
3. **면접 준비**: 스크리닝 결과 기반으로 예상 질문 준비
