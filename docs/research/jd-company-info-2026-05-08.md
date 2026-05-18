# JD Company Info Research - 2026-05-08

This note preserves public-source facts used to repair JD screening that was created before complete company info existed.

## DailyPay

Sources:
- Wanted company page: https://www.wanted.co.kr/company/48997
- Saramin company page: https://m.saramin.co.kr/job-search/company-info-view?csn=QjEvZUVHOXpCMVRsNFpSODIyL25Cdz09
- TheVC profile: https://thevc.kr/daily-pay
- ETNews Pre-A article: https://www.etnews.com/20250110000133

Facts captured:
- Founded in 2023.
- Business: SME/small-business early settlement / alternative finance.
- Headcount signals: 8 employees in TheVC; 11 employees in Saramin/National Pension snapshot.
- Wanted average salary: 5,308만원.
- Funding: Seed in 2024, Pre-A in 2025; investors include Primer, 유경피에스지자산운용, and TIPS.
- Screening implication: positive domain match, but very early-stage company and average salary suggest strong senior-compensation verification is needed.

## Samyang Foods

Sources:
- Wanted company page: https://www.wanted.co.kr/company/7406
- Official company introduction: https://www.samyangfoods.com/kor/information/company/index.do
- JobKorea company page: https://www.jobkorea.co.kr/company/1369701?tabType=I

Facts captured:
- Founded in 1961.
- Business: noodles, snacks, sauces, HMR/food manufacturing; KOSPI-listed.
- JobKorea headcount: 2,880 as of 2025-09-30.
- Wanted salary: 5,857만원 average; JobKorea college-graduate starting salary: 6,000만원.
- 2024 revenue signal: 1조 4,262억원.
- Screening implication: company stability improved after enrichment, but the AI backend JD still requires ML/DL, OCR, and LLM tuning as core requirements, so the final verdict remains negative on role fit.

## QMIT / PLCO

Sources:
- Wanted company page: https://www.wanted.co.kr/company/4980
- Wanted JD 356935: https://www.wanted.co.kr/wd/356935
- GroupBy startup page: https://groupby.kr/startups/2018
- Remember JD 309246: https://career.rememberapp.co.kr/job/posting/309246
- Saramin salary page: https://m.saramin.co.kr/salaries/total-salary/view/csn/5288600986/company_nm/%ED%81%90%EC%97%A0%EC%95%84%EC%9D%B4%ED%8B%B0

Facts captured:
- Founded in 2018.
- Business: sports-tech SaaS for sports teams, coaches, and players.
- Headcount signals: 47 employees in Wanted; 37 total / 9 developers in GroupBy.
- Salary signals: Wanted average salary 4,313만원; Saramin average salary 5,676만원.
- Funding signals are inconsistent across sources: Series A / Pre-Series B and 65~77억원 total funding. Record the inconsistency rather than normalizing it.
- Screening implication for 356935: technical stack matches backend experience. Treat the body requirement as "7+ years"; do not use the extractor's 7~10 year display as a hard upper-bound reason. Salary signals and broad architecture/infrastructure ownership keep it in hold status pending compensation and responsibility-scope verification.

## Neosapience / Typecast

Sources:
- Wanted company page: https://www.wanted.co.kr/company/4666
- Remember company page: https://career.rememberapp.co.kr/job/company/1471241
- JobKorea company page: https://www.jobkorea.co.kr/company/45475070
- JobKorea salary page: https://www.jobkorea.co.kr/company/45475070/salary
- Saramin finance page: https://www.saramin.co.kr/zf_user/company-info/view-inner-finance/csn/bFExeG9RSkwzQXF0RDcvNDJJdjhWQT09/company_nm/%EB%84%A4%EC%98%A4%EC%82%AC%ED%94%BC%EC%97%94%EC%8A%A4%28%EC%A3%BC%29
- Saramin salary page: https://www.saramin.co.kr/zf_user/company-info/view-inner-salary/csn/bFExeG9RSkwzQXF0RDcvNDJJdjhWQT09/company_nm/%EB%84%A4%EC%98%A4%EC%82%AC%ED%94%BC%EC%97%94%EC%8A%A4
- KM&A News funding article: https://www.kmnanews.com/news/articleView.html?idxno=9656
- beSUCCESS funding article: https://besuccess.com/?p=177861

Facts captured:
- Founded in 2017/2018 depending on source date granularity; company registration-style sources point to November 2017.
- Business: AI voice generation / synthetic media / Typecast content SaaS.
- Headcount signals: Wanted 56, Remember 57~58, JobKorea 64.
- Salary signals vary materially: Wanted 5,932만원, Remember 6,524만원, JobKorea 5,779만원, Saramin 8,667만원. Treat salary as source-sensitive rather than a single hard fact.
- Funding: Pre-IPO round, 165억원 newly raised, 427억원 cumulative funding, with InterVest, HB Investment, K2 Investment, and Bokwang Investment among participating investors.
- Screening implication for 361158: company-info completeness block was caused by extractor search failure on the parenthesized Wanted company name. Use the manually enriched `private/company_info/네오사피엔스-타입캐스트.md` file for screening.
