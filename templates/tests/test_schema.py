#!/usr/bin/env python3
"""Unit tests for schema validation."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "build"))

from schema import (
    extract_field,
    extract_section_items,
    validate_variant_tags,
    validate_contact,
    validate_profile,
    validate_project,
)


class TestExtractField(unittest.TestCase):
    def test_extract_existing_field(self):
        content = "# Title\n- Name: John Doe\n- Email: john@example.com"
        self.assertEqual(extract_field(content, 'Name'), 'John Doe')
        self.assertEqual(extract_field(content, 'Email'), 'john@example.com')

    def test_extract_missing_field(self):
        content = "# Title\n- Name: John Doe"
        self.assertIsNone(extract_field(content, 'Email'))

    def test_extract_field_with_colon_in_value(self):
        content = "- Period: 2023.01 - 현재"
        self.assertEqual(extract_field(content, 'Period'), '2023.01 - 현재')


class TestExtractSectionItems(unittest.TestCase):
    def test_extract_items(self):
        content = """## Tech Stack
- Python
- FastAPI
- PostgreSQL

## Other
- Item
"""
        items = extract_section_items(content, 'Tech Stack')
        self.assertEqual(items, ['Python', 'FastAPI', 'PostgreSQL'])

    def test_extract_empty_section(self):
        content = """## Tech Stack

## Other
- Item
"""
        items = extract_section_items(content, 'Tech Stack')
        self.assertEqual(items, [])

    def test_extract_missing_section(self):
        content = "## Other\n- Item"
        items = extract_section_items(content, 'Tech Stack')
        self.assertEqual(items, [])


class TestValidateVariantTags(unittest.TestCase):
    def test_valid_tags(self):
        content = """<!-- job-only:start -->
Content
<!-- job-only:end -->"""
        errors = validate_variant_tags(content, 'test.md')
        self.assertEqual(errors, [])

    def test_unclosed_tag(self):
        content = """<!-- job-only:start -->
Content"""
        errors = validate_variant_tags(content, 'test.md')
        self.assertEqual(len(errors), 1)
        self.assertIn('Unclosed', str(errors[0]))

    def test_unmatched_end_tag(self):
        content = """Content
<!-- job-only:end -->"""
        errors = validate_variant_tags(content, 'test.md')
        self.assertEqual(len(errors), 1)
        self.assertIn('without matching start', str(errors[0]))

    def test_multiple_valid_tags(self):
        content = """<!-- job-only:start -->
Job content
<!-- job-only:end -->

<!-- public-only:start -->
Public content
<!-- public-only:end -->"""
        errors = validate_variant_tags(content, 'test.md')
        self.assertEqual(errors, [])


class TestValidateContact(unittest.TestCase):
    def test_valid_contact(self):
        content = """# Contact
- Name: John Doe
- Email: john@example.com"""
        errors = validate_contact(content, 'contact.md')
        self.assertEqual(errors, [])

    def test_missing_name(self):
        content = """# Contact
- Email: john@example.com"""
        errors = validate_contact(content, 'contact.md')
        self.assertEqual(len(errors), 1)
        self.assertIn('Name', str(errors[0]))

    def test_invalid_email(self):
        content = """# Contact
- Name: John Doe
- Email: invalid-email"""
        errors = validate_contact(content, 'contact.md')
        self.assertEqual(len(errors), 1)
        self.assertIn('Email', str(errors[0]))


class TestValidateProfile(unittest.TestCase):
    def test_valid_profile(self):
        content = """# Company
- Period: 2023.01 - 현재
- Role: Backend Developer"""
        errors = validate_profile(content, 'profile.md')
        self.assertEqual(errors, [])

    def test_missing_period(self):
        content = """# Company
- Role: Backend Developer"""
        errors = validate_profile(content, 'profile.md')
        self.assertEqual(len(errors), 1)
        self.assertIn('Period', str(errors[0]))

    def test_invalid_period_format(self):
        content = """# Company
- Period: 2023 - 현재
- Role: Backend Developer"""
        errors = validate_profile(content, 'profile.md')
        self.assertEqual(len(errors), 1)
        self.assertIn('Period', str(errors[0]))

    def test_valid_period_with_end_date(self):
        content = """# Company
- Period: 2020.09 - 2023.01
- Role: Backend Developer"""
        errors = validate_profile(content, 'profile.md')
        self.assertEqual(errors, [])


class TestValidateProject(unittest.TestCase):
    def test_valid_project(self):
        content = """## Project Name

### Tech Stack
- Python
- FastAPI"""
        errors = validate_project(content, 'project.md')
        self.assertEqual(errors, [])

    def test_empty_tech_stack(self):
        content = """## Project Name

### Tech Stack

### Other"""
        errors = validate_project(content, 'project.md')
        self.assertEqual(len(errors), 1)
        self.assertIn('Tech Stack', str(errors[0]))

    def test_project_with_variant_tags(self):
        content = """## Project Name

### Tech Stack
- Python

<!-- job-only:start -->
Job specific content
<!-- job-only:end -->"""
        errors = validate_project(content, 'project.md')
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
