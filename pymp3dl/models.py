from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Track:
    number: int
    title: str
    track_page_url: str
    direct_url: str | None = None
    filename: str | None = None
    size_bytes: int | None = None
    downloaded: bool = False
    skipped: bool = False


@dataclass
class Album:
    slug: str
    title: str
    url: str
    tracks: list[Track] = field(default_factory=list)
    output_dir: Path = field(default_factory=lambda: Path("."))
