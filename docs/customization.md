# Customization

이력서 빌드 시스템의 커스터마이징 옵션입니다.

## Variant 시스템

두 가지 variant로 이력서를 생성할 수 있습니다:

| Variant | 용도 | 특징 |
|---------|------|------|
| `public` | 포트폴리오/공개용 | 상세 정보, 모든 회사 포함 |
| `job` | 지원용 | 간결함, 최근 경력 중심 |

### Variant 태그

마크다운 파일에서 variant별 콘텐츠를 구분합니다:

```markdown
<!-- public-only:start -->
상세 메트릭과 수치 (커밋 1,200+, DAU 10만+)
<!-- public-only:end -->

<!-- job-only:start -->
간결한 성과 요약
<!-- job-only:end -->
```

**중요**: 태그 형식을 정확히 지켜야 합니다. `<!-- variant:public -->` 같은 형식은 인식되지 않습니다.

## Override 시스템

특정 회사/포지션 지원 시 맞춤형 이력서를 생성합니다.

### 구조

```
overrides/
└── <target>/
    ├── config.json         # 설정 오버라이드
    ├── style.css           # 타겟별 CSS (선택사항)
    ├── profile/
    │   └── summary-job.md  # 파일 오버라이드
    └── companies/
        └── <company>/
            ├── profile.md
            └── projects/   # 디렉토리 오버라이드 (전체 교체)
                └── *.md
```

### config.json 예시

```json
{
  "job": {
    "companies": ["techcorp", "startup1"],
    "company_detail": {
      "startup1": "summary"
    },
    "include_awards": false
  }
}
```

### 파일 오버라이드

동일한 경로에 파일을 배치하면 원본 대신 사용됩니다:

```
# 원본
profile/summary-job.md

# 오버라이드 (targetco 지원 시)
overrides/targetco/profile/summary-job.md
```

### 디렉토리 오버라이드

`projects/` 또는 `achievements/` 디렉토리 전체를 오버라이드할 수 있습니다. `overrides/<target>/companies/<company>/projects/` 디렉토리가 존재하면, 해당 회사의 원본 `projects/` 전체를 대체합니다 (개별 파일 오버라이드가 아닌 디렉토리 단위 교체).

> **주의**: `full` 모드 회사는 모든 프로젝트 파일을 오버라이드해야 합니다. 일부 파일만 오버라이드하면 나머지는 원본(한국어 등)에서 그대로 가져옵니다.

### 빌드

```bash
./build.sh job full --target targetco
```

## 회사별 설정

`templates/build/resume_builder.py`의 `VARIANT_CONFIG`에서 설정합니다:

```python
VARIANT_CONFIG = {
    'public': {
        'companies': ['company1', 'company2', 'company3'],
        'include_certificates': True,
        'company_detail': {
            'company3': 'full',  # 상세 출력
        },
    },
    'job': {
        'companies': ['company1', 'company2'],
        'include_certificates': False,
        'company_detail': {
            'company2': 'summary',  # 요약만 출력
        },
    },
}
```

### company_detail 옵션

| 값 | 설명 |
|----|------|
| `full` | 프로필 + 프로젝트 + 성과 모두 출력 |
| `summary` | 프로필 개요만 출력 |

## 스타일 커스터마이징

### CSS 파일

- `templates/style.css` - 전체 이력서용
- `templates/style-short.css` - 1페이지 요약용

### 타겟별 스타일

`overrides/<target>/style.css`를 생성하면 해당 타겟 빌드 시 적용됩니다.

## 빌드 포맷

| 포맷 | 명령어 | 출력 |
|------|--------|------|
| 전체 | `./build.sh <variant> full` | PDF, HTML, MD, TXT |
| 요약 | `./build.sh <variant> short` | PDF, HTML, MD |
| Wanted | `./build.sh <variant> wanted` | TXT (채용사이트용) |
| 모두 | `./build.sh <variant> all` | 위 모든 포맷 |
