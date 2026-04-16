# Resume Builder

모듈화된 이력서 관리 시스템. Markdown 기반으로 이력서를 작성하고, 다양한 포맷(PDF, HTML, TXT)으로 빌드합니다.

## Features

- **Variant 시스템**: `public`(포트폴리오용)과 `job`(지원용) 두 가지 버전 관리
- **Override 시스템**: 지원 회사별 맞춤형 이력서 생성
- **다양한 출력 포맷**: PDF, HTML, Markdown, 채용사이트용 텍스트
- **Claude Code 연동**: AI 스킬로 채용공고 분석 및 이력서 최적화

## Quick Start

### Prerequisites

```bash
# macOS
brew install python pandoc
pip3 install weasyprint

# Ubuntu/Debian
sudo apt-get install python3 pandoc
pip3 install weasyprint
```

### 예제로 테스트

```bash
# 예제 데이터로 빌드
./build.sh example all

# 생성된 파일 확인
ls private/build/resume-example*
```

### 개인 데이터 설정

```bash
# 프로필 디렉토리 생성 후 예제 복사
mkdir -p private/profile private/companies
cp -r example/profile/* private/profile/
cp -r example/companies/* private/companies/

# 파일들을 개인 정보로 수정
# private/profile/contact.md, private/profile/summary-*.md 등
```

### 빌드

```bash
# 공개용 이력서 (포트폴리오)
./build.sh public all

# 지원용 이력서
./build.sh job all

# 특정 회사 타겟
./build.sh job full --target company-name
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
│   ├── build/            # 생성된 파일
│   └── variant_config.json
├── templates/            # 빌드 도구
│   ├── build/            # 빌드 스크립트 (resume_builder.py 등)
│   ├── jd/               # JD 파이프라인 스크립트
│   └── themes/           # CSS 스타일
├── example/              # 예제 데이터
└── docs/                 # 상세 문서
```

## Variant 시스템

마크다운에서 variant별 콘텐츠를 구분합니다:

```markdown
<!-- public-only:start -->
상세 메트릭 (커밋 1,200+, DAU 10만+)
<!-- public-only:end -->

<!-- job-only:start -->
간결한 성과 요약
<!-- job-only:end -->
```

## 문서

- [Getting Started](docs/getting-started.md) - 설치 및 빠른 시작
- [Customization](docs/customization.md) - variant, override 시스템
- [AI Workflow](docs/ai-workflow.md) - Claude Code 스킬 활용

## Claude Code 스킬

구직 활동을 위한 AI 스킬이 포함되어 있습니다:

| 스킬 | 설명 |
|------|------|
| `/extract-company-info` | 회사 정보 추출 |
| `/extract-recruitment-info` | 채용 정보 통합 추출 (회사 + JD) |
| `/extract-job-posting` | 채용공고 추출 |
| `/jd-screening` | JD 적합성 분석 |
| `/jd-batch` | 여러 채용공고 배치 처리 및 재분류 |
| `/resume-build` | 이력서 빌드 및 검증 |

자동화 스크립트:
- `python3 templates/jd/auto.py`: 검색 → JD 추출 → 회사정보 추출 → 스크리닝 → 자동 분류
- `python3 templates/jd/auto.py --from-urls <file>`: URL 파일 기반 배치 실행
- `python3 templates/jd/auto.py --screening-only --from-urls <file>`: 기존 JD 대상 스크리닝/분류만 수행
- `python3 templates/jd/auto.py --resume`: 이전 실행에서 미완료 항목만 재처리
- `python3 templates/jd/auto.py --dry-run`: 미리보기 모드
- `python3 templates/jd/auto.py --thevc-mode auto|skip|require`: 스타트업 투자정보(TheVC) 처리 정책 선택

자세한 사용법은 [AI Workflow](docs/ai-workflow.md)를 참고하세요.

## License

MIT License - see [LICENSE](LICENSE)
