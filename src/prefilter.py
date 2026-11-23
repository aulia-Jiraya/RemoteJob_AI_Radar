from __future__ import annotations
import re
from src.models import JobItem


def passes_prefilter(
    job: JobItem,
    include_patterns: list[str],
    exclude_patterns: list[str],
    title_patterns: list[str] | None = None,
) -> bool:
    haystack = f"{job.title}\n{job.location}\n{job.description}".lower()

    for neg in exclude_patterns:
        if re.search(neg, haystack, flags=re.IGNORECASE):
            return False

    if title_patterns:
        if not any(re.search(tp, job.title, flags=re.IGNORECASE) for tp in title_patterns):
            return False

    if not include_patterns:
        return True

    return any(re.search(pos, haystack, flags=re.IGNORECASE) for pos in include_patterns)
