#!/usr/bin/env python3
"""Contract tests for HTTP job posting extractors."""

import unittest


class TestWantedExtractorContract(unittest.TestCase):
    def test_extract_company_id_accepts_known_field_names(self):
        from wanted_extract import extract_company_id

        self.assertEqual(extract_company_id({"company_id": 15095}), 15095)
        self.assertEqual(extract_company_id({"id": 15095}), 15095)

    def test_extract_company_id_handles_missing_company_object(self):
        from wanted_extract import extract_company_id

        self.assertIsNone(extract_company_id("DeepSearch"))
        self.assertIsNone(extract_company_id({}))


class TestRememberExtractorContract(unittest.TestCase):
    def test_extract_posting_id_accepts_posting_and_short_job_urls(self):
        from remember_batch_extract import extract_posting_id

        self.assertEqual(
            extract_posting_id("https://career.rememberapp.co.kr/job/posting/123456"),
            "123456",
        )
        self.assertEqual(
            extract_posting_id("https://rememberapp.co.kr/job/123456"),
            "123456",
        )
        self.assertEqual(
            extract_posting_id("https://rememberapp.co.kr/job/123456?foo=bar"),
            "123456",
        )

    def test_extract_posting_id_rejects_company_urls(self):
        from remember_batch_extract import extract_posting_id

        self.assertIsNone(
            extract_posting_id("https://career.rememberapp.co.kr/job/company/123456")
        )


if __name__ == "__main__":
    unittest.main()
