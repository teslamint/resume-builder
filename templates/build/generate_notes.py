#!/usr/bin/env python3
"""Generate resume-job-notes.md from diff between base and current resume."""

import argparse
import difflib
from datetime import datetime
from pathlib import Path


def generate_diff(base_content: str, current_content: str) -> tuple[list[str], int, int]:
    """Generate unified diff and count additions/deletions."""
    base_lines = base_content.splitlines()
    current_lines = current_content.splitlines()

    diff = list(difflib.unified_diff(
        base_lines, current_lines,
        fromfile='resume-job-base.md',
        tofile='resume-job.md',
        lineterm='\n'
    ))

    additions = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
    deletions = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))

    return diff, additions, deletions


def format_notes_entry(target: str, diff_lines: list[str], additions: int, deletions: int, max_lines: int = 200) -> str:
    """Format a notes entry with diff."""
    date_str = datetime.now().strftime('%Y-%m-%d')

    if len(diff_lines) > max_lines:
        diff_content = f"(diff too large: {len(diff_lines)} lines, showing summary only)"
    else:
        diff_content = '\n'.join(line.rstrip('\n') for line in diff_lines)

    return f"""## {date_str} - Target: {target}

- 변경 요약: +{additions}/-{deletions} lines

```diff
{diff_content}
```

"""


def main():
    parser = argparse.ArgumentParser(description='Generate resume notes from diff')
    parser.add_argument('--base', required=True, help='Path to base resume markdown')
    parser.add_argument('--current', required=True, help='Path to current resume markdown')
    parser.add_argument('--target', default='TBD', help='Target company/job posting name')
    parser.add_argument('--clean', action='store_true', help='Overwrite notes file instead of append')
    parser.add_argument('--output', default='private/build/resume-job-notes.md', help='Output notes file path')
    args = parser.parse_args()

    base_path = Path(args.base)
    current_path = Path(args.current)
    output_path = Path(args.output)

    if not base_path.exists():
        print(f"Error: Base file not found: {base_path}")
        return 1

    if not current_path.exists():
        print(f"Error: Current file not found: {current_path}")
        return 1

    base_content = base_path.read_text(encoding='utf-8')
    current_content = current_path.read_text(encoding='utf-8')

    if base_content == current_content:
        print("No differences found between base and current resume.")
        return 0

    diff_lines, additions, deletions = generate_diff(base_content, current_content)
    entry = format_notes_entry(args.target, diff_lines, additions, deletions)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.clean or not output_path.exists():
        header = "# Resume Job Notes\n\n"
        output_path.write_text(header + entry, encoding='utf-8')
        print(f"Created: {output_path}")
    else:
        existing = output_path.read_text(encoding='utf-8')
        output_path.write_text(existing + entry, encoding='utf-8')
        print(f"Updated: {output_path}")

    print(f"Changes: +{additions}/-{deletions} lines")
    return 0


if __name__ == '__main__':
    exit(main())
