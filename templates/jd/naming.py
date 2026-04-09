#!/usr/bin/env python3
"""Canonical company name slugification and normalization.

Consolidates 7 scattered slugify/normalize variants into 2 parameterized
functions. Existing modules delegate here; callers don't need to change.
"""

import re

_LEGAL_ENTITY_RE = re.compile(
    r'\(주\)|주식회사|\(유\)|유한회사|㈜|\(주\)|Inc\.?|Corp\.?|Co\.,?\s*Ltd\.?',
    re.IGNORECASE,
)

_JU_PREFIX_RE = re.compile(r"\(주\)|\(주 \)")
_NON_ALNUM_HANGUL_RE = re.compile(r"[^a-zA-Z0-9가-힣]")


def slugify_company(
    name: str,
    *,
    max_len: int = 60,
    fallback: str = "unknown-company",
) -> str:
    """Filesystem-safe company name slug.

    Parameterized to cover all existing variants:
      - utils.slugify_company:           max_len=60, fallback="unknown-company"
      - wanted_extract.slugify:          max_len=50, fallback=""
      - remember_batch_extract.slugify:  max_len=50, fallback=""
      - check_companies.slugify:         max_len=50, fallback=""
    """
    text = _JU_PREFIX_RE.sub("", name or "").strip()
    text = _NON_ALNUM_HANGUL_RE.sub(" ", text).strip()
    result = "-".join(text.lower().split())[:max_len]
    return result or fallback


def normalize_company_name(name: str) -> str:
    """Normalize company name by removing legal entity suffixes.

    Uses the broadest regex (_LEGAL_ENTITY_RE) which handles:
    (주), 주식회사, (유), 유한회사, ㈜, Inc., Corp., Co. Ltd.

    NOT a replacement for:
      - company_extractor._normalize_company_name (narrower regex, strips spaces)
      - recollect_company_info.normalize_name_key (strips all non-alnum)
    Those have intentionally different semantics.
    """
    name = _LEGAL_ENTITY_RE.sub('', name)
    return re.sub(r'[\[\]\(\)]', '', name).strip().lower()
