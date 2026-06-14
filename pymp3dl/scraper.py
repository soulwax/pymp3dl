from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .models import Album, Track
from .utils import fetch_with_retry, sanitize_filename

BASE_URL = "https://downloads.khinsider.com"


def _find_format_col_index(headers: list[str], fmt: str) -> int:
    """Return the column index of the requested format header (case-insensitive)."""
    upper = fmt.upper()
    for i, h in enumerate(headers):
        if h.strip().upper() == upper:
            return i
    raise ValueError(f"No '{fmt}' column found in track table. Headers: {headers}")


async def scrape_album(url: str, client: httpx.AsyncClient, fmt: str = "mp3") -> Album:
    response = await fetch_with_retry(client, url)
    soup = BeautifulSoup(response.text, "lxml")

    title_tag = soup.find("h2")
    album_title = title_tag.get_text(strip=True) if title_tag else urlparse(url).path.split("/")[-1]

    slug = urlparse(url).path.rstrip("/").split("/")[-1]

    table = soup.find("table", id="songlist")
    if table is None:
        raise RuntimeError(f"Could not find #songlist table on {url}")

    header_row = table.find("tr")  # type: ignore[union-attr]
    if header_row is None:
        raise RuntimeError("Track table has no header row")

    headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
    fmt_col = _find_format_col_index(headers, fmt)

    tracks: list[Track] = []
    rows = table.find_all("tr")[1:]  # type: ignore[union-attr]
    for row in rows:
        tds = row.find_all("td")
        if len(tds) <= fmt_col:
            continue
        try:
            number_text = tds[0].get_text(strip=True).rstrip(".")
            number = int(number_text) if number_text.isdigit() else len(tracks) + 1
        except (ValueError, IndexError):
            number = len(tracks) + 1

        title = tds[1].get_text(strip=True) if len(tds) > 1 else f"Track {number}"

        link_tag = tds[fmt_col].find("a")
        if link_tag is None:
            continue
        track_page_url = urljoin(BASE_URL, link_tag["href"])

        tracks.append(Track(number=number, title=title, track_page_url=track_page_url))

    return Album(slug=slug, title=album_title, url=url, tracks=tracks)


async def scrape_track_page(track: Track, client: httpx.AsyncClient, fmt: str = "mp3") -> Track:
    response = await fetch_with_retry(client, track.track_page_url)
    soup = BeautifulSoup(response.text, "lxml")

    direct_url: str | None = None

    # Priority 1: <audio src="...">
    audio_tag = soup.find("audio")
    if audio_tag and audio_tag.get("src"):  # type: ignore[union-attr]
        direct_url = str(audio_tag["src"])  # type: ignore[index]

    # Priority 2: <a class="songDownloadLink">
    if direct_url is None:
        dl_link = soup.find("a", class_="songDownloadLink")
        if dl_link and dl_link.get("href"):  # type: ignore[union-attr]
            direct_url = str(dl_link["href"])  # type: ignore[index]

    # Priority 3: <p class="songDownloadLink"> containing an <a>
    if direct_url is None:
        p_tag = soup.find("p", class_="songDownloadLink")
        if p_tag:
            a_tag = p_tag.find("a")  # type: ignore[union-attr]
            if a_tag and a_tag.get("href"):
                direct_url = str(a_tag["href"])

    # Fallback: any <a href> ending in the desired format not on khinsider domain
    if direct_url is None:
        ext = f".{fmt}"
        for a_tag in soup.find_all("a", href=True):
            href = str(a_tag["href"])
            if href.lower().endswith(ext) and "khinsider.com" not in href:
                direct_url = href
                break

    if direct_url is None:
        raise RuntimeError(
            f"Could not find download URL on track page: {track.track_page_url}"
        )

    track.direct_url = direct_url
    track.filename = f"{track.number:03d} - {sanitize_filename(track.title)}.{fmt}"
    return track
