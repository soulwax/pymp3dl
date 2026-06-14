from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from .models import Album, Track
from .utils import fetch_with_retry, sanitize_filename

BASE_URL = "https://downloads.khinsider.com"


def _col_index(headers: list[str], *candidates: str) -> int | None:
    for i, h in enumerate(headers):
        if h.strip().upper() in {c.upper() for c in candidates}:
            return i
    return None


def _find_format_col_index(headers: list[str], fmt: str) -> int:
    idx = _col_index(headers, fmt)
    if idx is None:
        raise ValueError(f"No '{fmt}' column found in track table. Headers: {headers}")
    return idx


async def scrape_album(url: str, client: httpx.AsyncClient, fmt: str = "mp3") -> Album:
    response = await fetch_with_retry(client, url)
    soup = BeautifulSoup(response.text, "lxml")

    title_tag = soup.find("h2")
    album_title = (
        title_tag.get_text(strip=True)
        if isinstance(title_tag, Tag)
        else urlparse(url).path.split("/")[-1]
    )

    slug = urlparse(url).path.rstrip("/").split("/")[-1]

    table = soup.find("table", id="songlist")
    if not isinstance(table, Tag):
        raise RuntimeError(f"Could not find #songlist table on {url}")

    header_row = table.find("tr")
    if not isinstance(header_row, Tag):
        raise RuntimeError("Track table has no header row")

    headers = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]
    fmt_col = _find_format_col_index(headers, fmt)
    num_col = _col_index(headers, "#", "No.", "Number", "Track")
    title_col = _col_index(headers, "Song Name", "Name", "Title", "Song")

    tracks: list[Track] = []
    for row in table.find_all("tr")[1:]:
        if not isinstance(row, Tag):
            continue
        tds = row.find_all("td")
        if len(tds) <= fmt_col:
            continue

        if num_col is not None and len(tds) > num_col:
            raw = tds[num_col].get_text(strip=True).rstrip(".")
            number = int(raw) if raw.isdigit() else len(tracks) + 1
        else:
            number = len(tracks) + 1

        if title_col is not None and len(tds) > title_col:
            title = tds[title_col].get_text(strip=True)
        else:
            title = f"Track {number}"

        link_tag = tds[fmt_col].find("a")
        if not isinstance(link_tag, Tag):
            continue
        track_page_url = urljoin(BASE_URL, str(link_tag["href"]))

        tracks.append(Track(number=number, title=title, track_page_url=track_page_url))

    return Album(slug=slug, title=album_title, url=url, tracks=tracks)


async def scrape_track_page(track: Track, client: httpx.AsyncClient, fmt: str = "mp3") -> Track:
    response = await fetch_with_retry(client, track.track_page_url)
    soup = BeautifulSoup(response.text, "lxml")

    direct_url: str | None = None

    # Priority 1: <audio src="...">
    audio_tag = soup.find("audio")
    if isinstance(audio_tag, Tag) and audio_tag.get("src"):
        direct_url = str(audio_tag["src"])

    # Priority 2: <a class="songDownloadLink">
    if direct_url is None:
        dl_link = soup.find("a", class_="songDownloadLink")
        if isinstance(dl_link, Tag) and dl_link.get("href"):
            direct_url = str(dl_link["href"])

    # Priority 3: <p class="songDownloadLink"> containing an <a>
    if direct_url is None:
        p_tag = soup.find("p", class_="songDownloadLink")
        if isinstance(p_tag, Tag):
            a_tag = p_tag.find("a")
            if isinstance(a_tag, Tag) and a_tag.get("href"):
                direct_url = str(a_tag["href"])

    # Fallback: any <a href> ending in the desired format not on khinsider domain
    if direct_url is None:
        ext = f".{fmt}"
        for a_tag in soup.find_all("a", href=True):
            if not isinstance(a_tag, Tag):
                continue
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
