from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from pymp3dl.downloader import download_track
from pymp3dl.models import Track

CDN_URL = "https://vgmsite.com/soundtracks/golden-sun-the-lost-age/01%20Overture.mp3"


@pytest.mark.asyncio
async def test_download_track_writes_file(
    httpx_mock: HTTPXMock, tmp_path: Path
) -> None:
    fake_audio = b"\xff\xfb" + b"\x00" * 100  # minimal fake MP3 bytes
    httpx_mock.add_response(url=CDN_URL, content=fake_audio)

    track = Track(
        number=1,
        title="Overture",
        track_page_url="",
        direct_url=CDN_URL,
        filename="001 - Overture.mp3",
    )
    async with httpx.AsyncClient() as client:
        updated = await download_track(track, tmp_path, client, overwrite=True)

    dest = tmp_path / "001 - Overture.mp3"
    assert dest.exists()
    assert dest.read_bytes() == fake_audio
    assert updated.downloaded is True


@pytest.mark.asyncio
async def test_download_track_skips_existing(tmp_path: Path) -> None:
    dest = tmp_path / "001 - Overture.mp3"
    dest.write_bytes(b"existing")

    track = Track(
        number=1,
        title="Overture",
        track_page_url="",
        direct_url=CDN_URL,
        filename="001 - Overture.mp3",
    )
    async with httpx.AsyncClient() as client:
        updated = await download_track(track, tmp_path, client, overwrite=False)

    assert updated.skipped is True
    assert dest.read_bytes() == b"existing"
