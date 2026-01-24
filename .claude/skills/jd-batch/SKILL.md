---
name: jd-batch
description: This skill should be used when the user asks to "배치 처리", "JD 배치", "일괄 스크리닝", "batch screening", "URL 목록 처리", or wants to process multiple job postings at once
---

# JD 배치 처리 스킬

여러 채용공고를 일괄 처리합니다.

## 주요 기능

1. **URL 배치 처리**: URL 목록에서 중복 체크 및 추출 필요 여부 판별
2. **폴더 재분류**: 스크리닝 결과 기반 파일 자동 분류
3. **상태 확인**: 현재 JD 분류 현황 조회

## 사용법

### 1. URL 배치 처리

```bash
# URL 목록 파일 생성
cat > urls.txt << 'EOF'
https://www.wanted.co.kr/wd/123456
https://www.wanted.co.kr/wd/234567
https://rememberapp.co.kr/job/345678
EOF

# 배치 처리 실행
python3 templates/jd_pipeline.py --file urls.txt
```

출력 예시:
```
결과           ID         메시지
======================================================================
⏭️ duplicate  123456     이미 존재: 123456-company-position.md
📝 needs_manual 234567   추출 필요 (플랫폼: wanted)
📝 needs_manual 345678   추출 필요 (플랫폼: remember)
======================================================================
총 3건: 중복 1, 수동필요 2
```

### 2. 폴더 재분류

```bash
# 특정 폴더의 JD 파일들을 스크리닝 결과에 따라 재분류
python3 templates/jd_pipeline.py --rescreen job_postings/pass/

# 미리보기 (dry-run)
python3 templates/jd_pipeline.py --rescreen job_postings/pass/ --dry-run
```

### 3. 현재 상태 확인

```bash
python3 templates/jd_pipeline.py --status
```

출력 예시:
```
📊 JD 현황
========================================
  🔴 pass                  43건
  🟢 conditional/high       5건
  🟡 conditional/hold      10건
  ✅ applied                3건
========================================
  총계: 61건
```

## 워크플로우

### 새 URL 일괄 처리

1. URL 목록 파일 준비
2. `--file` 옵션으로 중복 체크
3. `needs_manual` 항목에 대해 `/extract-job-posting` 실행
4. 추출 완료 후 `/jd-screening` 실행
5. `--classify` 또는 `--rescreen`으로 자동 분류

### 기존 파일 재분류

1. 스크리닝 결과 파일이 `jd_analysis/screening/`에 있어야 함
2. `--rescreen` 또는 `--classify`로 판정 기반 분류

## 분류 매핑

| 판정 | 대상 폴더 |
|------|----------|
| 🟢 지원 추천 | `conditional/high/` |
| 🟡 지원 보류 | `conditional/hold/` |
| 🔴 지원 비추천 | `pass/` |

## 관련 스킬

- `/extract-job-posting` - 단일 URL 추출
- `/jd-screening` - 스크리닝 분석
- `/extract-company-info` - 회사 정보 수집
