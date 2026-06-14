from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def album_page_html() -> str:
    return (FIXTURES / "album_page.html").read_text(encoding="utf-8")


@pytest.fixture
def track_page_html() -> str:
    return (FIXTURES / "track_page.html").read_text(encoding="utf-8")
