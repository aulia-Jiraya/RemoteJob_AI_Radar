from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "source",
    "gh_src",
    "lever-source",
    "lever-origin",
    "fbclid",
    "gclid",
}


def normalize_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    clean_query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")
    ]
    clean_query.sort()
    return urlunparse((scheme, netloc, path, "", urlencode(clean_query), ""))


class JobStateStore:
    def __init__(self, path: str | Path, retention_days: int = 30) -> None:
        self.path = Path(path)
        self.retention_days = retention_days
        self.seen: dict[str, str] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.seen = {}
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.seen = data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            self.seen = {}
        self.prune()

    def prune(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        kept: dict[str, str] = {}
        removed = 0
        for url, ts_str in self.seen.items():
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= cutoff:
                    kept[url] = ts.isoformat()
                else:
                    removed += 1
            except ValueError:
                removed += 1
        self.seen = kept
        return removed

    def is_seen(self, url: str) -> bool:
        return normalize_url(url) in self.seen

    def mark_seen(self, url: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        self.seen[normalize_url(url)] = now_iso

    def save(self) -> None:
        self.prune()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.seen, indent=2, sort_keys=True),
            encoding="utf-8",
        )