#!/usr/bin/env python3
"""
Interview Sheet Builder for E-ink Tablets

인터뷰 준비 MD 파일을 전자잉크 태블릿용 PDF로 변환합니다.
8페이지 구조: Cover, Goal & Exit, My Positioning, Questions 1, Questions 2, Technical, Live Notes, Decision

Usage:
    python3 build-sheet.py <interview-md-file> [--stage STAGE]

Stage presets:
    실무    - Cover, Goal, Positioning, Q1, Tech, Notes
    심화    - Cover, Goal, Positioning, Q1, Q2, Tech, Notes
    컬처핏  - Cover, Goal, Positioning, Q1, Notes
    임원    - Cover, Goal, Positioning, Q2, Notes
    decision - Decision only

Example:
    python3 build-sheet.py interview.md              # 전체 8페이지
    python3 build-sheet.py interview.md --stage 실무  # 6페이지 (실무 인터뷰용)
"""

import sys
import re
import subprocess
import tempfile
import html
import argparse
from pathlib import Path
from datetime import datetime

SECTIONS = [
    ('sec-cover', 'COVER'),
    ('sec-goal', 'GOAL'),
    ('sec-position', 'POS'),
    ('sec-exp', 'EXP'),
    ('sec-q1', 'Q1'),
    ('sec-q2', 'Q2'),
    ('sec-tech', 'TECH'),
    ('sec-notes', 'NOTES'),
    ('sec-decision', 'GO/NO'),
]

STAGE_PRESETS = {
    '실무': ['sec-cover', 'sec-goal', 'sec-position', 'sec-exp', 'sec-q1', 'sec-tech', 'sec-notes'],
    '심화': ['sec-cover', 'sec-goal', 'sec-position', 'sec-exp', 'sec-q1', 'sec-q2', 'sec-tech', 'sec-notes'],
    '컬처핏': ['sec-cover', 'sec-goal', 'sec-position', 'sec-exp', 'sec-q1', 'sec-notes'],
    '임원': ['sec-cover', 'sec-goal', 'sec-position', 'sec-exp', 'sec-q2', 'sec-notes'],
    'decision': ['sec-decision'],
}


def build_tab_nav(current_section: str, active_pages: list[str] | None = None) -> str:
    """현재 섹션 기준 탭 내비게이션 HTML 생성"""
    nav_html = '<nav class="tab-nav">\n'
    for sec_id, label in SECTIONS:
        if active_pages is not None and sec_id not in active_pages:
            continue
        active = ' is-active' if sec_id == current_section else ''
        vertical_label = '<br>'.join(label)
        nav_html += f'<a class="tab{active}" href="#{sec_id}">{vertical_label}</a>\n'
    nav_html += '</nav>\n'
    return nav_html


def extract_table(content: str, after_heading: str) -> list[dict]:
    """테이블을 파싱하여 딕셔너리 리스트로 반환"""
    pattern = rf'{after_heading}\s*\n\s*\|[^\n]+\n\s*\|[-\s|]+\n((?:\s*\|[^\n]+\n)+)'
    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        return []

    table_text = match.group(0)
    lines = [l.strip() for l in table_text.strip().split('\n') if l.strip().startswith('|')]
    if len(lines) < 3:
        return []

    headers = [h.strip() for h in lines[0].split('|')[1:-1]]
    results = []
    for line in lines[2:]:
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if len(cells) == len(headers):
            results.append(dict(zip(headers, cells)))
    return results


def extract_section(content: str, heading: str, level: int = 2) -> str:
    """특정 헤딩의 섹션 내용 추출"""
    prefix = '#' * level
    pattern = rf'^{prefix}\s+{re.escape(heading)}.*?\n(.*?)(?=^{prefix}\s|\Z)'
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ''


def extract_subsection(content: str, heading: str) -> str:
    """### 레벨 서브섹션 추출"""
    pattern = rf'^###\s+{re.escape(heading)}.*?\n(.*?)(?=^###\s|^##\s|\Z)'
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ''


def extract_basic_info(content: str) -> dict:
    """기본 정보 테이블 파싱"""
    table = extract_table(content, r'## 기본 정보')
    info = {}
    for row in table:
        if '항목' in row and '내용' in row:
            info[row['항목']] = row['내용']
    return info


def extract_exit_signals(content: str) -> list[str]:
    """즉시 철수 신호 추출"""
    section = extract_subsection(content, '즉시 철수 신호')
    if not section:
        return []

    signals = []
    for line in section.split('\n'):
        line = line.strip()
        if line.startswith('- '):
            signal = line[2:].strip()
            signal = re.sub(r'\*\*([^*]+)\*\*', r'\1', signal)
            signals.append(signal)
    return signals


def extract_questions_by_category(content: str, categories: list[str]) -> dict[str, list[dict]]:
    """리스크 검증 질문을 카테고리별로 추출"""
    result = {}
    risk_section = extract_section(content, '1. 리스크 검증 질문')

    for category in categories:
        subsection = extract_subsection(risk_section, category) if risk_section else ''
        if subsection:
            table = extract_table(f'### {category}\n{subsection}', f'### {category}')
            result[category] = table
        else:
            result[category] = []
    return result


def extract_reverse_questions(content: str) -> list[str]:
    """역질문 리스트 추출"""
    section = extract_section(content, '5. 역질문 리스트')
    questions = []
    for line in section.split('\n'):
        line = line.strip()
        if line.startswith('- "') and line.endswith('"'):
            questions.append(line[3:-1])
        elif line.startswith('- '):
            questions.append(line[2:].strip('"'))
    return questions


def extract_technical_test(content: str) -> tuple[str, list[dict]]:
    """기술 테스트 (화이트보드/라이브 코딩) 섹션 추출

    Returns:
        tuple: (테스트 유형, 예상 유형 테이블)
    """
    section = extract_section(content, '2. 화이트보드 테스트 대비')
    if section:
        return ('화이트보드', extract_table(f'### 예상 유형\n{section}', '### 예상 유형'))

    section = extract_section(content, '2. 라이브 코딩 테스트 대비')
    if section:
        return ('라이브 코딩', extract_table(f'### 예상 유형\n{section}', '### 예상 유형'))

    return ('화이트보드', [])


def extract_positioning_warnings(content: str) -> dict:
    """주의사항 (금지/허용 표현) 추출"""
    org_section = extract_section(content, '3. 조직적합성 면접 대비')
    if not org_section:
        return {'forbidden': [], 'allowed': []}

    warnings = extract_subsection(org_section, '주의사항')
    forbidden = []
    allowed = []

    for line in warnings.split('\n'):
        line = line.strip()
        if line.startswith('- ❌'):
            text = line[4:].strip().strip('"')
            forbidden.append(text)
        elif line.startswith('- ⭕'):
            text = line[4:].strip().strip('"')
            allowed.append(text)

    return {'forbidden': forbidden, 'allowed': allowed}


def extract_positioning_qa(content: str) -> list[dict]:
    """포지셔닝 Q&A 추출 - 문서 전체에서 검색"""
    return extract_table(content, r'### \[My Positioning\] Q&A')


def extract_expected_questions(content: str) -> dict[str, list[dict]]:
    """예상 질문 & 답변 가이드 추출"""
    section = extract_section(content, '예상 질문 & 답변 가이드')
    if not section:
        return {}
    
    result = {}
    categories = ['기술 질문', '조직적합성 질문', '압박/포지셔닝 질문', 'KDL 맞춤 질문']
    for cat in categories:
        table = extract_table(f'### {cat}\n{section}', f'### {cat}')
        if table:
            result[cat] = table
    return result


def extract_decision_criteria(content: str) -> dict:
    """최종 판단 기준 추출"""
    section = extract_section(content, '8. 최종 판단 기준')

    required = []
    preferred = []
    current_list = None

    for line in section.split('\n'):
        line = line.strip()
        if '필수 조건' in line:
            current_list = required
        elif '우대 조건' in line:
            current_list = preferred
        elif line.startswith('- [ ]') and current_list is not None:
            item = line[5:].strip()
            current_list.append(item)

    return {'required': required, 'preferred': preferred}


def extract_motivation(content: str) -> str:
    """지원 서사 추출"""
    section = extract_section(content, '0. 왜')
    if not section:
        return ''

    match = re.search(r'>\s*"([^"]+)"', section)
    return match.group(1) if match else ''


def build_cover_page(info: dict, active_pages: list[str] | None = None) -> str:
    """Cover 페이지 생성"""
    company = info.get('회사명', 'Unknown Company')
    position = info.get('포지션', 'Unknown Position')
    stage = info.get('면접 단계', '')
    today = datetime.now().strftime('%Y-%m-%d')

    tab_nav = build_tab_nav('sec-cover', active_pages)
    return f'''<div id="sec-cover" class="cover page-break">
{tab_nav}
<h1>{company}</h1>
<div class="cover-info">
<p><strong>{position}</strong></p>
<p>{stage}</p>
</div>
<div class="cover-date">
<p>면접일: ________________</p>
<p>준비일: {today}</p>
</div>
</div>
'''


def build_goal_exit_page(motivation: str, exit_signals: list[str], active_pages: list[str] | None = None) -> str:
    """Goal & Exit 페이지 생성"""
    tab_nav = build_tab_nav('sec-goal', active_pages)
    html = f'''<div id="sec-goal" class="page-goal page-break">
{tab_nav}
<h2>Goal & Exit Signals</h2>

<h3>지원 서사 (한 문장)</h3>
<blockquote>
'''
    html += motivation if motivation else '(서사를 직접 작성하세요)'
    html += '''
</blockquote>

<h3>확인할 것 (4가지)</h3>
<div class="checkbox-item"><span class="checkbox"></span> <span>팀 안정성 (구조조정 배경, 팀 규모)</span></div>
<div class="checkbox-item"><span class="checkbox"></span> <span>업무 범위 (회색 영역 정의, 신규개발 vs 운영 비중)</span></div>
<div class="checkbox-item"><span class="checkbox"></span> <span>워라밸 (실제 근무시간, 온콜 체계)</span></div>
<div class="checkbox-item"><span class="checkbox"></span> <span>연봉 (범위 확인, 포괄임금 여부)</span></div>

<div class="memo-space-large"></div>

<h3>즉시 철수 신호 <span class="red-flag">🚩</span></h3>
<div class="warning-box">
'''
    for signal in exit_signals:
        html += f'<div class="checkbox-item"><span class="checkbox"></span> <span>{signal}</span></div>\n'

    if not exit_signals:
        html += '''<div class="checkbox-item"><span class="checkbox"></span> <span>(인터뷰 MD에서 추출 실패 - 직접 작성)</span></div>
'''

    html += '''</div>
</div>
'''
    return html


def build_positioning_page(warnings: dict, qa_list: list[dict], active_pages: list[str] | None = None) -> str:
    """My Positioning 페이지 생성"""
    tab_nav = build_tab_nav('sec-position', active_pages)
    out = f'''<div id="sec-position" class="page-positioning page-break">
{tab_nav}
<h2>My Positioning</h2>

<h3>핵심 포지셔닝</h3>
<blockquote>
"기술적 기여에 집중하는 시니어 IC를 지향합니다.<br>
신규 기능·초기 MVP 단계부터 운영 리스크와 변경 범위를 고려하며, 맡은 영역의 안정성과 품질을 책임지는 방식으로 일해왔습니다."
</blockquote>

<h3>추가 질문 대응</h3>
<table class="qa-table">
<tr><th>질문</th><th>답변 프레임</th></tr>
'''
    for row in qa_list:
        q = html.escape(row.get('질문', ''))
        a = html.escape(row.get('답변 프레임', ''))
        out += f'<tr><td>{q}</td><td>{a}</td></tr>\n'

    out += '''</table>

<h3>표현 가이드</h3>
<table class="expression-table">
<tr><th>❌ 금지</th><th>⭕ 허용</th></tr>
'''
    max_len = max(len(warnings['forbidden']), len(warnings['allowed']), 1)
    for i in range(max_len):
        forbidden = html.escape(warnings['forbidden'][i]) if i < len(warnings['forbidden']) else ''
        allowed = html.escape(warnings['allowed'][i]) if i < len(warnings['allowed']) else ''
        out += f'<tr><td class="do-not">{forbidden}</td><td>{allowed}</td></tr>\n'

    out += '''</table>
</div>
'''
    return out


def build_expected_questions_page(expected_qs: dict[str, list[dict]], active_pages: list[str] | None = None) -> str:
    """Expected Questions 페이지 (내가 받을 예상 질문)"""
    tab_nav = build_tab_nav('sec-exp', active_pages)
    out = f'''<div id="sec-exp" class="page-expected page-break">
{tab_nav}
<h2>예상 질문 & 답변</h2>
'''
    for category, questions in expected_qs.items():
        if questions:
            out += f'<h3>{category}</h3>\n<table>\n'
            # Get headers from first row
            if questions:
                headers = list(questions[0].keys())
                out += '<tr>' + ''.join(f'<th>{h}</th>' for h in headers) + '</tr>\n'
                for q in questions[:4]:  # Limit to 4 per category
                    out += '<tr>' + ''.join(f'<td>{html.escape(str(q.get(h, "")))}</td>' for h in headers) + '</tr>\n'
            out += '</table>\n'
    
    out += '</div>\n'
    return out


def build_questions_page_1(questions: dict[str, list[dict]], active_pages: list[str] | None = None) -> str:
    """Questions 1 페이지 (조직/업무/워라밸)"""
    tab_nav = build_tab_nav('sec-q1', active_pages)
    html = f'''<div id="sec-q1" class="page-questions page-break">
{tab_nav}
<h2>Questions 1: 조직/업무/워라밸</h2>
'''

    for category in ['조직 안정성', '업무 범위', '워라밸']:
        if category in questions and questions[category]:
            html += f'<h3>{category}</h3>\n'
            for q in questions[category][:2]:
                question = q.get('질문', '')
                intent = q.get('의도', '')
                html += f'''<div class="question-block">
<div class="question-text">{question}</div>
<div class="question-intent">의도: {intent}</div>
<div class="question-memo"></div>
</div>
'''

    html += '</div>\n'
    return html


def build_questions_page_2(questions: dict[str, list[dict]], reverse_questions: list[str], active_pages: list[str] | None = None) -> str:
    """Questions 2 페이지 (연봉 + 역질문)"""
    tab_nav = build_tab_nav('sec-q2', active_pages)
    html = f'''<div id="sec-q2" class="page-questions page-break">
{tab_nav}
<h2>Questions 2: 연봉/역질문</h2>

<h3>연봉 확인</h3>
'''

    if '연봉' in questions and questions['연봉']:
        for q in questions['연봉']:
            question = q.get('질문', '')
            intent = q.get('의도', '')
            html += f'''<div class="question-block">
<div class="question-text">{question}</div>
<div class="question-intent">의도: {intent}</div>
<div class="question-memo"></div>
</div>
'''

    html += '<h3>역질문 (선택)</h3>\n'
    for q in reverse_questions[:4]:
        html += f'''<div class="question-block">
<div class="question-text">{q}</div>
<div class="question-memo"></div>
</div>
'''

    html += '</div>\n'
    return html


def build_technical_page(test_type: str, test_items: list[dict], active_pages: list[str] | None = None) -> str:
    """Technical 페이지"""
    tab_nav = build_tab_nav('sec-tech', active_pages)
    html = f'''<div id="sec-tech" class="page-technical page-break">
{tab_nav}
<h2>Technical: {test_type}</h2>

<h3>예상 유형</h3>
<table>
<tr><th>유형</th><th>가능성</th><th>맥락</th></tr>
'''
    for t in test_items:
        type_name = t.get('유형', '')
        likelihood = t.get('가능성', '')
        context = t.get('KDL 맥락', t.get('맥락', ''))
        html += f'<tr><td>{type_name}</td><td>{likelihood}</td><td>{context}</td></tr>\n'

    html += '''</table>

<h3>설명 프레임</h3>
<ol>
<li>요구사항 확인 ("~라고 이해했는데 맞나요?")</li>
<li>고수준 아키텍처 그리기</li>
<li>각 컴포넌트 설명</li>
<li>트레이드오프 논의</li>
<li>병목/장애 대응</li>
</ol>

<h3>다이어그램 공간</h3>
<div class="diagram-space"></div>
</div>
'''
    return html


def build_live_notes_page(active_pages: list[str] | None = None) -> str:
    """Live Notes 페이지 (100% 필기용)"""
    tab_nav = build_tab_nav('sec-notes', active_pages)
    return f'''<div id="sec-notes" class="page-break">
{tab_nav}
<h2>Live Notes</h2>
<table class="notes-table">
<tr><th class="time-col">시간</th><th class="question-col">질문/주제</th><th class="notes-col">느낀점/위험신호</th></tr>
<tr><td></td><td></td><td></td></tr>
<tr><td></td><td></td><td></td></tr>
<tr><td></td><td></td><td></td></tr>
<tr><td></td><td></td><td></td></tr>
<tr><td></td><td></td><td></td></tr>
<tr><td></td><td></td><td></td></tr>
<tr><td></td><td></td><td></td></tr>
<tr><td></td><td></td><td></td></tr>
</table>
</div>
'''


def build_decision_page(criteria: dict, active_pages: list[str] | None = None) -> str:
    """Decision 페이지"""
    tab_nav = build_tab_nav('sec-decision', active_pages)
    html = f'''<div id="sec-decision" class="page-break">
{tab_nav}
<h2>Decision</h2>

<h3>필수 조건 체크</h3>
<div class="decision-box">
'''
    for item in criteria['required']:
        html += f'<div class="checkbox-item"><span class="checkbox"></span> <span>{item}</span></div>\n'

    html += '''</div>

<h3>우대 조건 체크</h3>
<div class="decision-box">
'''
    for item in criteria['preferred']:
        html += f'<div class="checkbox-item"><span class="checkbox"></span> <span>{item}</span></div>\n'

    html += '''</div>

<h3>철수 신호 감지</h3>
<div class="memo-space-large"></div>

<div class="decision-result">
<h3>최종 판단</h3>
<p>
<span class="checkbox"></span> <strong>GO</strong> &nbsp;&nbsp;&nbsp;&nbsp;
<span class="checkbox"></span> <strong>NO-GO</strong> &nbsp;&nbsp;&nbsp;&nbsp;
<span class="checkbox"></span> <strong>보류 (추가 확인 필요)</strong>
</p>
</div>

<h3>메모</h3>
<div class="memo-space-large"></div>
<div class="memo-space-large"></div>
</div>
'''
    return html


def build_html(md_content: str, css_path: Path, pages: list[str] | None = None) -> str:
    """전체 HTML 생성. pages가 None이면 전체, 아니면 해당 페이지만 빌드."""
    info = extract_basic_info(md_content)
    motivation = extract_motivation(md_content)
    exit_signals = extract_exit_signals(md_content)
    warnings = extract_positioning_warnings(md_content)
    positioning_qa = extract_positioning_qa(md_content)
    expected_qs = extract_expected_questions(md_content)
    questions = extract_questions_by_category(md_content, ['조직 안정성', '업무 범위', '워라밸', '연봉'])
    reverse_questions = extract_reverse_questions(md_content)
    test_type, test_items = extract_technical_test(md_content)
    criteria = extract_decision_criteria(md_content)

    out_html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Interview Sheet - {info.get('회사명', 'Unknown')}</title>
<link rel="stylesheet" href="{css_path}">
</head>
<body>
'''

    if pages is None or 'sec-cover' in pages:
        out_html += build_cover_page(info, pages)
    if pages is None or 'sec-goal' in pages:
        out_html += build_goal_exit_page(motivation, exit_signals, pages)
    if pages is None or 'sec-position' in pages:
        out_html += build_positioning_page(warnings, positioning_qa, pages)
    if pages is None or 'sec-exp' in pages:
        out_html += build_expected_questions_page(expected_qs, pages)
    if pages is None or 'sec-q1' in pages:
        out_html += build_questions_page_1(questions, pages)
    if pages is None or 'sec-q2' in pages:
        out_html += build_questions_page_2(questions, reverse_questions, pages)
    if pages is None or 'sec-tech' in pages:
        out_html += build_technical_page(test_type, test_items, pages)
    if pages is None or 'sec-notes' in pages:
        out_html += build_live_notes_page(pages)
    if pages is None or 'sec-decision' in pages:
        out_html += build_decision_page(criteria, pages)

    out_html += '''</body>
</html>
'''
    return out_html


def main():
    parser = argparse.ArgumentParser(
        description='인터뷰 준비 MD 파일을 전자잉크 태블릿용 PDF로 변환합니다.',
        epilog='예: python3 build-sheet.py interview.md --stage 실무'
    )
    parser.add_argument('input', help='인터뷰 MD 파일 경로')
    parser.add_argument(
        '--stage',
        choices=list(STAGE_PRESETS.keys()),
        help='인터뷰 단계 프리셋 (실무/심화/컬처핏/임원/decision)'
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    script_dir = Path(__file__).parent
    css_path = script_dir / 'style-sheet.css'

    if not css_path.exists():
        print(f"Error: CSS file not found: {css_path}")
        sys.exit(1)

    pages = STAGE_PRESETS.get(args.stage) if args.stage else None
    suffix = f'-sheet-{args.stage}' if args.stage else '-sheet'
    output_path = input_path.with_name(input_path.stem + suffix + '.pdf')

    md_content = input_path.read_text(encoding='utf-8')
    html_content = build_html(md_content, css_path, pages)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
        f.write(html_content)
        temp_html = Path(f.name)

    try:
        subprocess.run(
            ['weasyprint', str(temp_html), str(output_path)],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"Generated: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error generating PDF: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: weasyprint not found. Install with: pip install weasyprint")
        sys.exit(1)
    finally:
        temp_html.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
