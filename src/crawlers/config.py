from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CrawlerConfig:
    enabled_crawlers: list[str]
    linkedin: dict[str, Any] = field(default_factory=dict)
    facebook: dict[str, Any] = field(default_factory=dict)
    rate_limiting: dict[str, Any] = field(default_factory=lambda: {"min_delay": 2, "max_delay": 5})
    output: dict[str, Any] = field(default_factory=lambda: {
        "generate_resume": True,
        "generate_cover_letter": True,
        "style": "Classic",
    })

    EXPERIENCE_LEVEL_MAP = {
        "internship": 1,
        "entry": 2,
        "associate": 3,
        "mid-senior": 4,
        "director": 5,
        "executive": 6,
    }

    DATE_POSTED_MAP = {
        "past_24h": "r86400",
        "past_week": "r604800",
        "past_month": "r2592000",
    }

    JOB_TYPE_MAP = {
        "full-time": "F",
        "contract": "C",
        "part-time": "P",
        "temporary": "T",
        "internship": "I",
        "volunteer": "V",
        "other": "O",
    }

    WORK_TYPE_MAP = {
        "on-site": 1,
        "remote": 2,
        "hybrid": 3,
    }

    @classmethod
    def load(cls, path: Path) -> "CrawlerConfig":
        if not path.exists():
            raise FileNotFoundError(f"Crawler config not found: {path}")
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        if not data or "enabled_crawlers" not in data:
            raise ValueError("Crawler config must contain 'enabled_crawlers' key")
        return cls(
            enabled_crawlers=data["enabled_crawlers"],
            linkedin=data.get("linkedin", {}),
            facebook=data.get("facebook", {}),
            rate_limiting=data.get("rate_limiting", {"min_delay": 2, "max_delay": 5}),
            output=data.get("output", {
                "generate_resume": True,
                "generate_cover_letter": True,
                "style": "Classic",
            }),
        )
