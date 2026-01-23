---
name: extract-recruitment-info
description: This skill should be used when the user asks to "extract recruitment info", "채용 정보 추출", "회사 정보", "기업 정보", "job posting", "채용 공고", or provides any recruitment platform URL or company name
---

# 채용/기업 정보 통합 추출 스킬

Chrome MCP를 사용하여 여러 채용 플랫폼에서 채용 공고 및 기업 정보를 자동으로 검색하고 추출합니다.

## 사전 요구사항

1. Chrome MCP 확장 설치
2. 각 플랫폼 로그인 (Remember, Wanted 등 - 필요시)

## 핵심 기능

### 1. 자동 검색 (URL 없이 회사명/포지션만으로)

회사명만 제공되면 아래 플랫폼들을 자동 검색:

| 플랫폼 | 검색 URL | 추출 대상 |
|--------|----------|-----------|
| Wanted | `wanted.co.kr/search?query={name}&tab=company` | 연봉, 인원, 매출 |
| Remember | `career.rememberapp.co.kr/search?keyword={name}` | 연봉, 채용 |
| Saramin | `saramin.co.kr/zf_user/search?searchword={name}` | 연봉, 복지, 면접후기 |
| JobKorea | `jobkorea.co.kr/Search/?stext={name}` | 채용, 기업리뷰 |
| TheVC | `thevc.kr/search?query={name}` | 투자, 라운드, 연혁 |
| 점프잇 | `jumpit.saramin.co.kr/search?keyword={name}` | 채용, 기술스택 |

### 2. 채용 공고 추출

제공된 URL 또는 검색 결과에서:
- 포지션명, 경력 요건
- 자격요건, 우대사항
- 기술 스택, 업무 내용
- 복지/혜택

### 3. 기업 정보 추출 (멀티소스 병합)

#### 연봉 정보 (우선순위: Remember > Wanted > Saramin)

| 항목 | 데이터 포인트 |
|------|---------------|
| 평균 연봉 | 전체 평균 |
| 신입 예상 연봉 | 학력별 (고졸/초대졸/대졸/대학원) |
| 경력 예상 연봉 | 연차별 (2-4년/5-7년/8-10년/10년+) |
| 경력별 제보 연봉 | Wanted 모달에서 탭별 제보 내역 (경력구간, 기준연도, 금액) |
| 올해 입사자 평균 | 최근 입사자 기준 |

#### 투자 정보 (TheVC - 스타트업 전용)

| 항목 | 데이터 포인트 |
|------|---------------|
| 현재 라운드 | Seed/Pre-A/Series A/B/C/... |
| 누적 투자금 | 총액 |
| 투자자 | 주요 투자사 목록 |
| 투자 이력 | 라운드별 일자, 금액, 투자사 |
| 특허/R&D | 보유 특허, 국가 R&D 수 |

#### 기업 기본 정보

- 업종, 설립연도, 직원수
- 위치, 홈페이지
- 매출 추이 (연도별)
- 인원 증감 (입사/퇴사)

## 워크플로우

### Phase 1: 입력 분석

```
입력 유형 판별:
1. URL 제공 → 해당 플랫폼 직접 접근
2. 회사명만 제공 → 자동 검색 모드
3. 채용공고 URL → 회사 정보도 함께 추출
```

### Phase 2: 멀티소스 검색 (자동 검색 모드)

```
1. tabs_context_mcp로 탭 컨텍스트 확보
2. tabs_create_mcp로 새 탭 생성
3. 각 플랫폼 순차 검색:
   a. navigate로 검색 페이지 이동
   b. computer(screenshot)으로 결과 확인
   c. 회사 프로필 페이지 식별 및 클릭
   d. 상세 페이지에서 데이터 추출
```

### Phase 3: 데이터 추출

#### Wanted 추출
```
1. navigate → wanted.co.kr/company/{id}
2. computer(scroll, down, 5) × 3회
3. get_page_text로 텍스트 추출
4. 파싱: 연봉, 인원, 매출, 채용포지션
5. 경력별 제보 연봉 추출:
   a. "경력 예상연봉" 섹션의 "자세히 보기" 버튼 클릭
   b. 모달 창에서 각 탭(2-4년, 5-7년, 8-10년, 10년 초과) 순차 클릭
   c. 각 탭의 "제보 내역" 테이블에서 기준연도, 제보연봉 추출
   d. 제보가 있는 탭의 경력 구간과 연봉 매핑하여 저장
```

#### Remember 추출
```
1. navigate → career.rememberapp.co.kr/job/company/{id}
2. computer(scroll, down, 5) × 3회
3. get_page_text로 텍스트 추출
4. 파싱: 연봉, 채용포지션
```

#### Saramin 추출
```
1. navigate → saramin.co.kr/zf_user/company-info/view?csn={id}
2. computer(scroll, down, 5) × 2회
3. get_page_text로 텍스트 추출
4. 파싱: 연봉, 복지, 면접후기, 기업태그
```

#### TheVC 추출 (스타트업)
```
1. navigate → thevc.kr/{company_slug}
2. computer(screenshot)으로 기본 정보 확인
3. "투자 유치" 탭 클릭:
   javascript_tool(action: "javascript_exec",
     text: "document.evaluate(\"//a[contains(text(),'투자 유치')]\",
       document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null)
       .singleNodeValue.click()")
4. get_page_text로 투자 이력 추출
```

### Phase 4: 데이터 병합 및 정규화

```
1. 각 소스 데이터 수집
2. 필드별 우선순위 적용:
   - 연봉: Remember > Wanted > Saramin
   - 투자: TheVC only
   - 인원: Wanted > Saramin
   - 복지: Saramin > Wanted
3. 중복 제거 및 병합
4. 마크다운 포맷 생성
```

### Phase 5: 저장

```
채용공고: job_postings/{id}-{company}-{position}.md
기업정보: company_info/{company_slug}.md
```

## 출력 포맷

### 기업 정보 (company_info/*.md)

```markdown
# {회사명} ({영문명})

## 기업 정보

| 항목 | 내용 |
|------|------|
| 회사명 | (주){회사명} |
| 업종 | {업종} |
| 설립 | {YYYY년} ({N}년차) |
| 직원수 | {N}명 |
| 위치 | {주소} |
| 홈페이지 | {URL} |

## 연봉 정보

| 항목 | 금액 | 출처 |
|------|------|------|
| 평균 연봉 | **{N}만원** | {출처} |
| 작년 대비 | {+/-N}만원 ({+/-N}%) | {출처} |

### 신입 예상연봉

| 학력 | 예상 연봉 |
|------|----------|
| 고졸 | ± {N}만원 |
| 초대졸 | ± {N}만원 |
| 대졸 | ± {N}만원 |
| 대학원졸 | ± {N}만원 |

### 경력 예상연봉

| 경력 | 예상 연봉 |
|------|----------|
| 2-4년 | ± {N}만원 |
| 5-7년 | ± {N}만원 |
| 8-10년 | ± {N}만원 |
| 10년 초과 | ± {N}만원 |

### 제보 연봉 ({YYYY}년)

| 경력 | 제보 연봉 |
|------|----------|
| {N-M}년 | {N}만원 |
| {N-M}년 | {N}만원 |
| ... | ... |

> 참고: Wanted "경력 예상연봉" > "자세히 보기" > 각 탭별 "제보 내역"에서 추출

## 인원 통계

| 항목 | 수치 |
|------|------|
| 현재 인원 | {N}명 |
| 1년간 입사자 | {N}명 |
| 1년간 퇴사자 | {N}명 |
| 평균 근속연수 | {N}년 |

## 투자 정보 (스타트업)

| 항목 | 내용 |
|------|------|
| 현재 라운드 | {Series X} |
| 누적 투자금 | {N}억원 |
| 총 투자자 수 | {N}개사 |

### 투자 라운드 상세

| 라운드 | 일자 | 금액 | 투자자 |
|--------|------|------|--------|
| Series C | YYYY-MM-DD | {N}억원 | {투자사} |
| Series B | YYYY-MM-DD | {N}억원 | {투자사} |
| ... | ... | ... | ... |

## 복지/혜택

### 태그
- {태그1}
- {태그2}

### 복지 상세
**지원금/보험:**
- {항목}

**근무 환경:**
- {항목}

## 채용 중인 포지션

1. **{포지션명}**: {위치}, 경력 {N-M}년, {마감}
2. ...

## 회사 소개

{회사 소개 텍스트}

---

*추출일: {YYYY-MM-DD}*
*출처:*
- {URL1}
- {URL2}
- {URL3}
```

### 채용 공고 (job_postings/*.md)

```markdown
# {포지션명}

## Status

- [ ] 지원 전
- [ ] 서류 검토 중
- [ ] 면접 진행 중
- [ ] 최종 결과 대기
- [ ] 합격
- [ ] 불합격
- [ ] 보류

## 기본 정보

| 항목 | 내용 |
|------|------|
| 회사명 | {회사명} |
| 포지션 | {포지션명} |
| 경력 | {N-M}년 |
| 고용형태 | {정규직/계약직} |
| 근무지 | {주소} |
| 마감 | {일자/상시} |
| 원본 URL | {URL} |

## 주요 업무

- {업무1}
- {업무2}

## 자격요건

- {요건1}
- {요건2}

## 우대사항

- {우대1}
- {우대2}

## 기술 스택

- {기술1}
- {기술2}

## 혜택 및 복지

- {복지1}
- {복지2}

---

*추출일: {YYYY-MM-DD}*
```

## 점프잇 추출 방법

### URL 패턴
- 채용공고: `jumpit.saramin.co.kr/position/{id}`
- 회사검색: `jumpit.saramin.co.kr/search?keyword={name}`

### 추출 전략

```
1. navigate → jumpit.saramin.co.kr/position/{id}
2. computer(scroll, down, 3) × 2회
3. get_page_text로 텍스트 추출
4. 파싱: 포지션, 기술스택, 자격요건, 우대사항
```

### 추출 데이터 포인트
- 포지션명
- 경력 요건
- 기술 스택 (태그 형식)
- 자격요건
- 우대사항
- 회사 정보 링크

## 에러 처리

### 검색 결과 없음
```
"{회사명}"에 대한 검색 결과가 없습니다.
- 정확한 회사명 확인
- 영문/한글 변환 시도
- 직접 URL 제공 요청
```

### 비공개 정보
```
일부 정보가 비공개입니다:
- 연봉: [비공개] (업계 평균 {N}만원)
- 매출: 정보 없음
```

### 플랫폼 접근 제한
```
{플랫폼}에서 일시적 접근 제한이 발생했습니다.
다른 소스에서 추출을 계속합니다.
```

### 탭 컨텍스트 손실
```
tabs_context_mcp 재호출 후 createIfEmpty: true로 새 탭 생성
```

## 사용 예시

### 예시 1: 회사명만 제공
```
사용자: "엘박스 회사 정보 알려줘"

1. Wanted 검색 → 회사 페이지 발견 → 데이터 추출
2. Remember 검색 → 회사 페이지 발견 → 데이터 추출
3. TheVC 검색 → 스타트업 확인 → 투자 정보 추출
4. 데이터 병합 → company_info/lbox.md 저장
```

### 예시 2: 채용공고 URL 제공
```
사용자: "이 공고 정보 추출해줘: https://www.wanted.co.kr/wd/281470"

1. 채용공고 페이지 접근 → 공고 정보 추출
2. 회사 ID 추출 → 회사 정보 페이지 접근
3. 기업 정보 추출 (Wanted)
4. TheVC 검색 → 스타트업이면 투자 정보 추가
5. job_postings/{id}.md + company_info/{company}.md 저장
```

### 예시 3: 멀티 URL 제공
```
사용자: "아래 URL들에서 기업 정보 추출해줘:
- https://www.wanted.co.kr/company/10997
- https://career.rememberapp.co.kr/job/company/2344515
- https://thevc.kr/lbox"

1. 각 URL 순차 접근
2. 각 소스에서 데이터 추출
3. 데이터 병합 → company_info/lbox.md 저장
```

## 플랫폼별 특이사항

### Wanted
- 연봉 순위 (상위 N%) 제공
- 채용 중인 포지션 목록
- 유사 기업 추천
- **경력별 제보 연봉**: "경력 예상연봉" > "자세히 보기" 클릭 시 모달에서 탭별(2-4년/5-7년/8-10년/10년초과) 제보 내역 확인 가능

### Remember
- 작년 대비 연봉 변화율
- 상세한 연봉 통계

### Saramin
- 면접 후기 (난이도, 질문)
- 복지 태그 상세
- 국민연금 기반 데이터

### TheVC
- 투자 라운드 상세 이력
- 투자자/투자사 정보
- B2G 계약, 국가 R&D, 특허 수
- 스타트업 랭킹
- 관계사 정보

## 참고

- 연봉 데이터는 국민연금/건강보험 기반 추정치일 수 있음
- 일부 정보는 플랫폼 로그인 필요
- TheVC는 스타트업/벤처 기업만 등록됨
