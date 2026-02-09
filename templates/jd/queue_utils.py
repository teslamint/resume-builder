#!/usr/bin/env python3
"""
JD Queue Utilities - Shared queue operations with file locking.

Provides thread-safe queue operations for search_quick.py and worker.py.
Uses fcntl for file locking to prevent race conditions.
"""

import fcntl
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent
QUEUE_PATH = BASE_DIR / "job_postings" / "queue.json"


@dataclass
class QueueItem:
    """Item in the processing queue."""
    job_id: str
    url: str
    title: str
    company: str
    experience: str
    query: str
    discovered_at: str
    status: str = "pending"  # pending, processing, done, failed

    def to_dict(self) -> dict:
        return asdict(self)


def load_queue(with_stats: bool = False) -> Union[List[dict], Tuple[List[dict], dict]]:
    """
    Load queue with shared lock (LOCK_SH).

    Args:
        with_stats: If True, return (items, stats) tuple

    Returns:
        List of queue items, or (items, stats) if with_stats=True
    """
    if not QUEUE_PATH.exists():
        return ([], {}) if with_stats else []

    try:
        with open(QUEUE_PATH, "r", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                data = json.load(f)
                items = data.get("items", [])
                stats = data.get("stats", {})
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        return (items, stats) if with_stats else items
    except json.JSONDecodeError as e:
        logger.debug(f"Queue JSON decode error: {e}")
        return ([], {}) if with_stats else []
    except Exception as e:
        logger.debug(f"Queue load error: {e}")
        return ([], {}) if with_stats else []


def save_queue(items: List[dict], stats: Optional[dict] = None) -> bool:
    """
    Save queue with exclusive lock (LOCK_EX).

    Args:
        items: List of queue items
        stats: Optional stats dict to include

    Returns:
        True if save succeeded, False otherwise
    """
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "updated_at": datetime.now().isoformat(),
        "stats": stats or {},
        "items": items,
    }

    try:
        with open(QUEUE_PATH, "w", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=2, ensure_ascii=False)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return True
    except Exception as e:
        logger.error(f"Queue save error: {e}")
        return False


def update_item_status(
    job_id: str,
    status: str,
    result: Optional[str] = None
) -> bool:
    """
    Atomically update a single item's status with exclusive lock.

    Args:
        job_id: Job ID to update
        status: New status (pending, processing, done, failed)
        result: Optional result message

    Returns:
        True if update succeeded, False otherwise
    """
    if not QUEUE_PATH.exists():
        return False

    try:
        with open(QUEUE_PATH, "r+", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                data = json.load(f)
                items = data.get("items", [])

                for item in items:
                    if item.get("job_id") == job_id:
                        item["status"] = status
                        item["processed_at"] = datetime.now().isoformat()
                        if result:
                            item["result"] = result
                        break

                data["items"] = items
                data["updated_at"] = datetime.now().isoformat()

                f.seek(0)
                f.truncate()
                json.dump(data, f, indent=2, ensure_ascii=False)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return True
    except Exception as e:
        logger.error(f"Queue item update error: {e}")
        return False
