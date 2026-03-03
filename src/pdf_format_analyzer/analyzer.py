"""Vision LLM analysis of rendered PDF pages via GitHub Copilot SDK."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

from copilot import CopilotClient

from pdf_format_analyzer.config import PFAConfig
from pdf_format_analyzer.models import (
    BoundingBox,
    IssueCategory,
    PageImage,
    PageIssue,
    Severity,
)
from pdf_format_analyzer.prompts import BATCH_ANALYSIS_PROMPT, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def _encode_image(page: PageImage) -> str:
    """Encode page image bytes to base64 data URI."""
    return base64.b64encode(page.image_bytes).decode("ascii")


def _build_vision_messages(
    pages: list[PageImage],
) -> list[dict[str, Any]]:
    """Build chat messages with embedded images for vision analysis."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]

    content_parts: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": BATCH_ANALYSIS_PROMPT.format(count=len(pages)),
        },
    ]

    for page in pages:
        content_parts.append({
            "type": "text",
            "text": f"--- Page {page.page_number} ---",
        })
        content_parts.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{_encode_image(page)}",
            },
        })

    messages.append({"role": "user", "content": content_parts})
    return messages


def _parse_issues_response(raw: str, pages: list[PageImage]) -> list[PageIssue]:
    """Parse the LLM JSON response into PageIssue objects."""
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM response as JSON: %s...", text[:200])
        return []

    if not isinstance(data, list):
        data = [data]

    valid_pages = {p.page_number for p in pages}
    issues: list[PageIssue] = []

    for item in data:
        try:
            page_num = int(item.get("page_number", 0))
            if page_num not in valid_pages:
                continue

            severity_str = item.get("severity", "warning").lower()
            try:
                severity = Severity(severity_str)
            except ValueError:
                severity = Severity.WARNING

            category_str = item.get("category", "other").lower()
            try:
                category = IssueCategory(category_str)
            except ValueError:
                category = IssueCategory.OTHER

            bbox = None
            if "bounding_box" in item and item["bounding_box"]:
                bb = item["bounding_box"]
                bbox = BoundingBox(
                    x=float(bb.get("x", 0)),
                    y=float(bb.get("y", 0)),
                    width=float(bb.get("width", 0)),
                    height=float(bb.get("height", 0)),
                )

            issues.append(
                PageIssue(
                    page_number=page_num,
                    severity=severity,
                    category=category,
                    description=item.get("description", "Unknown issue"),
                    bounding_box=bbox,
                    confidence=float(item.get("confidence", 0.8)),
                )
            )
        except (ValueError, TypeError, KeyError) as exc:
            logger.debug("Skipping malformed issue entry: %s", exc)
            continue

    return issues


async def _analyze_batch(
    client: CopilotClient,
    pages: list[PageImage],
    model: str,
) -> list[PageIssue]:
    """Analyze a batch of pages with the vision LLM."""
    messages = _build_vision_messages(pages)

    logger.info(
        "Analyzing %d pages (pages %s) with model %s",
        len(pages),
        ", ".join(str(p.page_number) for p in pages),
        model,
    )

    content_parts: list[str] = []

    async def on_event(event: dict) -> None:
        event_type = event.get("type", "")
        if event_type == "assistant.message_delta":
            delta = event.get("delta", "")
            if delta:
                content_parts.append(delta)

    session = await client.new_session(model=model)
    session.on_event = on_event

    for msg in messages:
        await session.send_message(msg)

    # Wait for the session to become idle
    await session.wait_for_idle()

    raw_response = "".join(content_parts)
    return _parse_issues_response(raw_response, pages)


async def analyze_pages(
    pages: list[PageImage],
    config: PFAConfig | None = None,
) -> list[PageIssue]:
    """Analyze rendered PDF pages for formatting issues.

    Sends pages to a vision LLM in batches and returns detected issues.

    Args:
        pages: List of rendered page images.
        config: Optional configuration (uses defaults if not provided).

    Returns:
        List of detected formatting issues.
    """
    if not pages:
        return []

    cfg = config or PFAConfig()
    batch_size = cfg.batch_size
    model = cfg.model

    client = CopilotClient()
    await client.start()

    all_issues: list[PageIssue] = []

    # Process pages in batches
    for i in range(0, len(pages), batch_size):
        batch = pages[i : i + batch_size]
        try:
            issues = await _analyze_batch(client, batch, model)
            all_issues.extend(issues)
            logger.info("Batch found %d issues", len(issues))
        except Exception as exc:
            logger.error("Batch analysis failed for pages %d-%d: %s",
                         batch[0].page_number, batch[-1].page_number, exc)

    logger.info("Total issues found: %d", len(all_issues))
    return all_issues


def analyze_pages_sync(
    pages: list[PageImage],
    config: PFAConfig | None = None,
) -> list[PageIssue]:
    """Synchronous wrapper for analyze_pages."""
    return asyncio.run(analyze_pages(pages, config))
