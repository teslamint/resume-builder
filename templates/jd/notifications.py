"""Notification functions — send messages via openclaw CLI.

Extracted from auto.py for reuse by worker.py and other pipeline components.
"""
from __future__ import annotations

import subprocess
from datetime import datetime
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from auto import AutoTaskResult, RunSummary


def send_notification(message: str, config: dict) -> bool:
    """Send a notification via openclaw CLI."""
    notifications = config.get("notifications", {})
    channel = notifications.get("channel")
    target = notifications.get("target")
    account = notifications.get("account")
    if not channel:
        print("   ⚠️  알림 채널 미설정")
        return False
    if not target:
        print("   ⚠️  알림 대상 미설정 (notifications.target)")
        return False

    try:
        command = [
            "openclaw",
            "message",
            "send",
            "--channel",
            channel,
            "--target",
            str(target),
            "--message",
            message,
        ]
        if account:
            command.extend(["--account", str(account)])
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print(f"   ✅ 알림 전송 완료 ({channel}:{target})")
            return True
        error_output = result.stderr.strip() or result.stdout.strip() or "unknown error"
        print(f"   ⚠️  알림 전송 실패: {error_output}")
        return False
    except FileNotFoundError:
        print("   ⚠️  openclaw 명령 없음 - 알림 스킵")
        return False
    except Exception as exc:
        print(f"   ⚠️  알림 오류: {exc}")
        return False


def format_notification(results: List, summary) -> str:
    """Format pipeline results as a notification message."""
    lines = [
        "🔔 **JD 자동 파이프라인 결과**",
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"✨ 신규 URL: {summary.new}개",
        f"✅ 처리 완료: {summary.processed}개",
        f"🟢 추천: {summary.recommended}개",
        f"🟡 보류: {summary.hold}개",
        f"🔴 패스: {summary.passed}개",
        "",
    ]

    recommended = [r for r in results if getattr(r, "verdict", None) == "지원 추천"]
    if recommended:
        lines.append("**🟢 지원 추천 공고:**")
        for row in recommended[:5]:
            title = getattr(row, "title", None) or getattr(row, "job_id", "unknown")
            company = getattr(row, "company", None) or "unknown"
            lines.append(f"• [{company}] {title}")
            lines.append(f"  {row.url}")
        if len(recommended) > 5:
            lines.append(f"  ... 외 {len(recommended) - 5}개")

    return "\n".join(lines)
