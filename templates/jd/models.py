"""Shared domain models — leaf module, no local imports."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DiscoveredJob:
    """Core job posting identity shared between search and queue paths."""
    job_id: str
    url: str
    title: str
    company: str
    experience: str
