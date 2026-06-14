import httpx
import pytest
from pytest_httpx import HTTPXMock

from pymp3dl.models import Track
from pymp3dl.scraper import scrape_album, scrape_track_page

ALBUM_URL = "https://downloads.khinsider.com/game-soundtracks/album/golden-sun-the-lost-age"
TRACK_PAGE_URL = (
    "https://downloads.khinsider.com/game-soundtracks/album/"
    "golden-sun-the-lost-age/01%20Overture.mp3"
)
CDN_URL = "https://vgmsite.com/soundtracks/golden-sun-the-lost-age/01%20Overture.mp3"


@pytest.mark.asyncio
async def test_scrape_album_parses_tracks(httpx_mock: HTTPXMock, album_page_html: str) -> None:
    httpx_mock.add_response(url=ALBUM_URL, text=album_page_html)

    async with httpx.AsyncClient() as client:
        album = await scrape_album(ALBUM_URL, client)

    assert album.title == "Golden Sun: The Lost Age"
    assert len(album.tracks) == 3
    assert album.tracks[0].title == "Overture"
    assert album.tracks[1].number == 2
    assert "01%20Overture.mp3" in album.tracks[0].track_page_url


@pytest.mark.asyncio
async def test_scrape_track_page_extracts_cdn_url(
    httpx_mock: HTTPXMock, track_page_html: str
) -> None:
    httpx_mock.add_response(url=TRACK_PAGE_URL, text=track_page_html)

    track = Track(number=1, title="Overture", track_page_url=TRACK_PAGE_URL)
    async with httpx.AsyncClient() as client:
        updated = await scrape_track_page(track, client)

    assert updated.direct_url == CDN_URL
    assert updated.filename == "001 - Overture.mp3"
