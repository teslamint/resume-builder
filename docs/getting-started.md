# Getting Started

이력서 빌드 시스템을 사용하기 위한 빠른 시작 가이드입니다.

## Prerequisites

다음 도구들이 설치되어 있어야 합니다:

- **Python 3.8+**
- **Pandoc** - Markdown을 HTML로 변환
- **WeasyPrint** - HTML을 PDF로 변환

### macOS

```bash
brew install python pandoc
pip3 install weasyprint
```

### Ubuntu/Debian

```bash
sudo apt-get install python3 pandoc
pip3 install weasyprint
```

## Quick Start

### 1. 예제로 테스트

먼저 예제 데이터로 빌드를 테스트합니다:

```bash
./build.sh example all
```

생성된 파일:
- `private/build/resume-example.pdf` - 전체 이력서
- `private/build/resume-example-short.pdf` - 1페이지 요약
- `private/build/resume-example-wanted.txt` - 채용 사이트용 텍스트

### 2. 개인 데이터 설정

`example/` 디렉토리를 참고하여 개인 데이터를 생성합니다:

```bash
# 프로필 디렉토리 생성
mkdir -p private/profile

# 예제에서 복사하여 수정
cp example/profile/*.md private/profile/
# 이후 private/profile/*.md 파일들을 개인 정보로 수정
```

자세한 설정 방법은 [USER_DATA.md](../USER_DATA.md)를 참고하세요.

### 3. 개인 이력서 빌드

```bash
# 공개용 (포트폴리오)
./build.sh public all

# 지원용
./build.sh job all
```

## 디렉토리 구조

```
resume/
├── private/              # 개인 데이터 (gitignored)
│   ├── profile/          # 개인 프로필 (연락처, 요약, 기술스택)
│   ├── companies/        # 경력 정보
│   │   └── <company>/
│   │       ├── profile.md
│   │       └── projects/
│   ├── overrides/        # 타겟별 오버라이드
│   │   └── <target>/
│   └── build/            # 생성된 파일
├── templates/            # 빌드 도구
│   ├── build/            # resume_builder.py 등
│   └── themes/           # CSS 스타일
├── example/              # 예제 데이터
└── docs/                 # 문서
```

## 다음 단계

- [JD Automation](#jd-automation-optional) - 채용공고 자동 수집/분석 파이프라인
- [Customization](customization.md) - variant 시스템과 오버라이드 설정
- [AI Workflow](ai-workflow.md) - Claude Code 스킬 활용

## JD Automation (Optional)

이력서 빌드 외에, 채용공고 자동 처리 파이프라인을 사용할 수 있습니다.

```bash
# 전체 자동화: 검색 → JD 추출 → 회사정보 → 스크리닝 → 분류
python3 templates/jd/auto.py

# 검색 없이 URL 파일로 실행
python3 templates/jd/auto.py --from-urls private/job_postings/unprocessed/search_YYYYMMDD_HHMM.txt

# 스타트업 투자정보(TheVC) 처리 정책
python3 templates/jd/auto.py --thevc-mode auto|skip|require

# 이전 실행에서 미완료 항목만 재처리
python3 templates/jd/auto.py --resume
```

주요 출력:
- `private/job_postings/auto_results/auto_<run_id>.json`
- `private/job_postings/unprocessed/company_enrichment_thevc.txt`
