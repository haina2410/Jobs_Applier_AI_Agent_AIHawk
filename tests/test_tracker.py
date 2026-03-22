import json
import tempfile
from pathlib import Path
from src.crawlers.tracker import Tracker


def test_filter_unseen_returns_new_jobs():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"linkedin_111": {"url": "http://old", "role": "Old", "crawled_at": "2026-01-01T00:00:00"}}, f)
        path = Path(f.name)
    tracker = Tracker(path)
    results = [
        {"id": "linkedin_111", "url": "http://old", "role": "Old"},
        {"id": "linkedin_222", "url": "http://new", "role": "New"},
    ]
    unseen = tracker.filter_unseen(results)
    assert len(unseen) == 1
    assert unseen[0]["id"] == "linkedin_222"
    path.unlink()


def test_mark_seen_persists():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({}, f)
        path = Path(f.name)
    tracker = Tracker(path)
    tracker.mark_seen("linkedin_333", "http://example.com")
    tracker2 = Tracker(path)
    assert "linkedin_333" in tracker2.seen
    path.unlink()


def test_empty_file_creates_fresh_tracker(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("")
    tracker = Tracker(path)
    assert tracker.seen == {}


def test_nonexistent_file_creates_fresh_tracker(tmp_path):
    path = tmp_path / "does_not_exist.json"
    tracker = Tracker(path)
    assert tracker.seen == {}
    tracker.mark_seen("linkedin_1", "http://example.com")
    assert path.exists()
