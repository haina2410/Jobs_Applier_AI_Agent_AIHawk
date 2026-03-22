import json
from datetime import datetime, timezone
from pathlib import Path

from src.logging import logger


class Tracker:
    """Tracks seen jobs in a JSON file to avoid reprocessing across runs."""

    def __init__(self, path: Path):
        self.path = path
        self.seen = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            text = self.path.read_text()
            if not text.strip():
                return {}
            return json.loads(text)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load tracker file {self.path}: {e}")
            return {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.seen, indent=2))
        tmp.rename(self.path)

    def filter_unseen(self, results: list[dict]) -> list[dict]:
        return [r for r in results if r["id"] not in self.seen]

    def mark_seen(self, job_id: str, url: str, role: str = "", company: str = "",
                  location: str = "", description: str = "", source: str = ""):
        self.seen[job_id] = {
            "url": url,
            "role": role,
            "company": company,
            "location": location,
            "description": description[:500] if description else "",
            "source": source,
            "crawled_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()
