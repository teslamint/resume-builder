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
python3 templates/jd/pipeline.py --file urls.txt
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
python3 templates/jd/pipeline.py --rescreen job_postings/pass/

# 미리보기 (dry-run)
python3 templates/jd/pipeline.py --rescreen job_postings/pass/ --dry-run
```

### 3. 현재 상태 확인

```bash
python3 templates/jd/pipeline.py --status
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

## 통합 파이프라인 (자동화)

URL 입력 시 **채용공고 추출 → 기업 정보 추출 → 스크리닝 → 자동 분류**를 한 번에 처리합니다.

### 파이프라인 단계

| Phase | 작업 | 도구 |
|-------|------|------|
| 1 | 중복 체크 | `jd_pipeline.py --url` |
| 2 | JD 추출 | Chrome MCP (navigate → get_page_text) |
| 3 | 회사 정보 | company_info/ 확인 → 없으면 WebSearch + WebFetch |
| 4 | 스크리닝 | jd-screening-rules.md 로드 → LLM 분석 |
| 5 | 자동 분류 | `jd_pipeline.py --classify` |

### Phase 1: 중복 체크

```bash
python3 templates/jd/pipeline.py --url "{URL}"
```

- `duplicate` → 기존 파일 경로 출력, 종료
- `needs_manual` → Phase 2 진행

### Phase 2: JD 추출

Chrome MCP 사용:

1. `tabs_context_mcp` 호출 (탭 컨텍스트 확인)
2. `tabs_create_mcp` 또는 기존 탭에서 `navigate` (url)
3. 페이지 로드 대기 후 `get_page_text` 호출
4. 채용공고 정보 파싱 (플랫폼별 구조 적용)
5. `job_postings/unprocessed/{id}-{company}-{position}.md` 저장

**플랫폼별 참조:**
- Wanted: `/extract-job-posting` 스킬의 Wanted 섹션 참조
- Remember: `/extract-job-posting` 스킬의 Remember 섹션 참조

### Phase 3: 회사 정보

1. `company_info/{company}.md` 존재 확인 (Glob 사용)
2. 없으면:
   - WebSearch로 회사 정보 검색
   - WebFetch로 상세 정보 수집
   - `/extract-company-info` 스킬 형식으로 저장
3. 있으면 스킵 (기존 파일 사용)

### Phase 4: 스크리닝

1. `job_postings/jd-screening-rules.md` 로드
2. `company_info/{company}.md` 로드 (있으면)
3. 6가지 기준 분석:
   - 기업 안정성
   - 연봉 구조
   - 업무 적합성
   - 개발 환경
   - 기타 우대조건
   - 채용 프로세스
4. `jd_analysis/screening/{id}-{company}-{position}.md` 저장
5. `jd_analysis/screening/SUMMARY.md` 업데이트

### Phase 5: 자동 분류

```bash
python3 templates/jd/pipeline.py --classify job_postings/unprocessed/
```

판정에 따라 자동 이동:
- 🟢 지원 추천 → `conditional/high/`
- 🟡 지원 보류 → `conditional/hold/`
- 🔴 지원 비추천 → `pass/`

### 에러 핸들링

| 상황 | 처리 |
|------|------|
| JD 추출 실패 | 사용자에게 수동 입력 요청, 해당 URL 스킵 |
| 회사 정보 없음 | 경고 출력 후 스크리닝 계속 (제한된 정보로 분석) |
| 스크리닝 실패 | `conditional/hold/`로 기본 분류 |
| Chrome 연결 실패 | 브라우저 확인 요청 후 대기 |

### 배치 처리

여러 URL 처리 시:

1. 각 URL에 대해 Phase 1~5 순차 실행
2. 중간 실패 시 해당 URL만 스킵, 나머지 계속
3. 최종 요약 테이블 출력:

```
처리 결과 요약
======================================================================
URL                                    상태      분류
----------------------------------------------------------------------
wanted.co.kr/wd/123456                ✅ 완료   conditional/high/
wanted.co.kr/wd/234567                ✅ 완료   pass/
rememberapp.co.kr/job/345678          ⏭️ 중복   (기존 파일)
wanted.co.kr/wd/456789                ❌ 실패   JD 추출 오류
======================================================================
총 4건: 성공 2, 중복 1, 실패 1
```

---

## 수동 워크플로우 (개별 실행)

### 새 URL 일괄 처리

1. URL 목록 파일 준비
2. `--file` 옵션으로 중복 체크
3. `needs_manual` 항목에 대해 `/extract-job-posting` 실행
4. **`/extract-company-info` 로 회사 정보 추출** (스크리닝 품질 향상)
5. `/jd-screening` 실행 (회사 정보 참조하여 분석)
6. `--classify` 또는 `--rescreen`으로 자동 분류

> **회사 정보가 있으면:**
> - 매출/인원 데이터로 회사 안정성 정확히 판단
> - 연봉 데이터로 연봉 구조 리스크 확인
> - 투자 정보로 스타트업 조건 충족 여부 검증

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
