#!/usr/bin/env python3
"""Schema validation for resume markdown files."""
import argparse
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent

SCHEMAS = {
    'contact': {
        'required_fields': ['Name', 'Email'],
        'patterns': {
            'Email': r'[\w.-]+@[\w.-]+\.\w+',
        },
    },
    'profile': {
        'required_fields': ['Period', 'Role'],
        'patterns': {
            'Period': r'\d{4}\.\d{2}\s*-\s*(\d{4}\.\d{2}|현재)',
        },
    },
    'project': {
        'required_sections': ['Tech Stack'],
        'min_items': {
            'Tech Stack': 1,
        },
    },
}

VARIANT_TAGS = [
    ('<!-- job-only:start -->', '<!-- job-only:end -->'),
    ('<!-- public-only:start -->', '<!-- public-only:end -->'),
    ('<!-- common:start -->', '<!-- common:end -->'),
]


class ValidationError:
    def __init__(self, file_path: str, message: str, line: int | None = None):
        self.file_path = file_path
        self.message = message
        self.line = line

    def __str__(self):
        if self.line:
            return f"{self.file_path}:{self.line}: {self.message}"
        return f"{self.file_path}: {self.message}"


def extract_field(content: str, field: str) -> str | None:
    """Extract field value from markdown content."""
    pattern = rf'^-\s*{field}:\s*(.+)$'
    match = re.search(pattern, content, re.MULTILINE)
    return match.group(1).strip() if match else None


def extract_section_items(content: str, section: str) -> list[str]:
    """Extract list items from a section."""
    lines = content.split('\n')
    items = []
    in_section = False

    for line in lines:
        if line.startswith('## ') or line.startswith('### '):
            section_name = line.lstrip('#').strip()
            if section_name == section:
                in_section = True
                continue
            elif in_section:
                break
        elif in_section and line.startswith('- '):
            items.append(line[2:].strip())

    return items


def validate_variant_tags(content: str, file_path: str) -> list[ValidationError]:
    """Validate that variant tags are properly paired."""
    errors = []
    lines = content.split('\n')

    for start_tag, end_tag in VARIANT_TAGS:
        tag_name = start_tag.replace('<!-- ', '').replace(':start -->', '')
        open_stack = []

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped == start_tag:
                open_stack.append(i)
            elif stripped == end_tag:
                if not open_stack:
                    errors.append(ValidationError(
                        file_path,
                        f"'{end_tag}' without matching start tag",
                        i
                    ))
                else:
                    open_stack.pop()

        for line_num in open_stack:
            errors.append(ValidationError(
                file_path,
                f"Unclosed '{tag_name}' block",
                line_num
            ))

    return errors


def validate_contact(content: str, file_path: str) -> list[ValidationError]:
    """Validate contact.md schema."""
    errors = []
    schema = SCHEMAS['contact']

    for field in schema['required_fields']:
        value = extract_field(content, field)
        if not value:
            errors.append(ValidationError(file_path, f"Missing required field: {field}"))
        elif field in schema.get('patterns', {}):
            pattern = schema['patterns'][field]
            if not re.search(pattern, value):
                errors.append(ValidationError(
                    file_path,
                    f"Invalid {field} format: '{value}' (expected pattern: {pattern})"
                ))

    return errors


def validate_profile(content: str, file_path: str) -> list[ValidationError]:
    """Validate company profile.md schema."""
    errors = []
    schema = SCHEMAS['profile']

    for field in schema['required_fields']:
        value = extract_field(content, field)
        if not value:
            errors.append(ValidationError(file_path, f"Missing required field: {field}"))
        elif field in schema.get('patterns', {}):
            pattern = schema['patterns'][field]
            if not re.search(pattern, value):
                errors.append(ValidationError(
                    file_path,
                    f"Invalid {field} format: '{value}' (expected pattern: {pattern})"
                ))

    errors.extend(validate_variant_tags(content, file_path))
    return errors


def validate_project(content: str, file_path: str) -> list[ValidationError]:
    """Validate project file schema."""
    errors = []
    schema = SCHEMAS['project']

    for section in schema.get('required_sections', []):
        items = extract_section_items(content, section)
        min_count = schema.get('min_items', {}).get(section, 0)
        if len(items) < min_count:
            errors.append(ValidationError(
                file_path,
                f"Section '{section}' requires at least {min_count} item(s), found {len(items)}"
            ))

    errors.extend(validate_variant_tags(content, file_path))
    return errors


def validate_file(file_path: Path) -> list[ValidationError]:
    """Validate a single file based on its type."""
    if not file_path.exists():
        return [ValidationError(str(file_path), "File not found")]

    content = file_path.read_text(encoding='utf-8')
    path_str = str(file_path)

    if file_path.name == 'contact.md':
        return validate_contact(content, path_str)
    elif file_path.name == 'profile.md' and 'companies' in path_str:
        return validate_profile(content, path_str)
    elif 'projects' in path_str and file_path.suffix == '.md':
        return validate_project(content, path_str)
    else:
        return validate_variant_tags(content, path_str)


def validate_all(base_dir: Path | None = None, example: bool = False) -> list[ValidationError]:
    """Validate all markdown files in the project."""
    if base_dir is None:
        base_dir = BASE_DIR / 'example' if example else BASE_DIR

    errors = []

    contact = base_dir / 'profile' / 'contact.md'
    if contact.exists():
        errors.extend(validate_file(contact))

    companies_dir = base_dir / 'companies'
    if companies_dir.exists():
        for company_dir in companies_dir.iterdir():
            if not company_dir.is_dir():
                continue

            profile = company_dir / 'profile.md'
            if profile.exists():
                errors.extend(validate_file(profile))

            projects_dir = company_dir / 'projects'
            if projects_dir.exists():
                for project_file in projects_dir.glob('*.md'):
                    if project_file.name != 'CLAUDE.md':
                        errors.extend(validate_file(project_file))

    return errors


def main():
    parser = argparse.ArgumentParser(description='Validate resume markdown files')
    parser.add_argument('--validate-all', action='store_true',
                        help='Validate all files in the project')
    parser.add_argument('--example', action='store_true',
                        help='Validate example data instead of real data')
    parser.add_argument('files', nargs='*', help='Specific files to validate')
    args = parser.parse_args()

    errors = []

    if args.validate_all:
        errors = validate_all(example=args.example)
    elif args.files:
        for file_path in args.files:
            errors.extend(validate_file(Path(file_path)))
    else:
        parser.print_help()
        return

    if errors:
        print("Validation errors found:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        sys.exit(1)
    else:
        print("All validations passed.")


if __name__ == '__main__':
    main()
