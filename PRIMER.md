# pymp3dl — Claude Primer

A complete specification for Claude (or any capable LLM) to implement `pymp3dl`: a smart, installable Python CLI tool for downloading MP3 files from khinsider-style album pages.

---

## Project Identity

| Field | Value |
|---|---|
| **Package name** | `pymp3dl` |
| **PyPI name** | `pymp3dl` |
| **CLI entrypoint** | `pymp3dl` |
| **Python requirement** | `>=3.11` |
| **License** | MIT |
| **Author** | soulwax |
| **GitHub** | `https://github.com/soulwax/pymp3dl` |

---

## What It Does

`pymp3dl` downloads MP3 (and optionally FLAC) audio files from khinsider.com album pages. The site uses a **two-level indirection pattern**:

1. **Album page** (e.g. `https://downloads.khinsider.com/game-soundtracks/album/golden-sun-the-lost-age`)  
   → Contains an HTML `<table>` with track rows. Each `<td>` in the "MP3" column holds an `<a>` tag linking to a **track page**, not directly to the MP3 file.

2. **Track page** (e.g. `https://downloads.khinsider.com/game-soundtracks/album/golden-sun-the-lost-age/02%20Main%20Theme.mp3`)  
   → This HTML page contains a direct `<a>` download link with `href` pointing to the actual hosted `.mp3` file (usually on a CDN like `https://vgmsite.com/...`).

Mass downloading from the album page directly does **not** work — you must visit each track page individually to extract the real download URL. This two-step scraping is the core logic.

### Site Structure Observations (from live analysis)

- Album page URL pattern: `/game-soundtracks/album/{album-slug}`
- Track links in the table: `<td class="playlistDownloadSong"><a href="/game-soundtracks/album/{slug}/{encoded-filename}.mp3">`
- On the track page, the real CDN link is inside: `<a class="songDownloadLink">` or a `<p>` element containing the audio source. The actual `<audio src="...">` tag or direct `<a href="https://vgmsite.com/...">` gives the downloadable URL.
- The site may return 403 or redirect to a login page when accessed without proper headers or cookies.
- Rate limiting: requests must be throttled (default 1–2 seconds between requests).
- Cookies can be required for authenticated/premium content.

---

## Project Layout

```
pymp3dl/
├── pymp3dl/
│   ├── __init__.py          # version, __all__
│   ├── cli.py               # Click entrypoints
│   ├── scraper.py           # HTML parsing, URL extraction
│   ├── downloader.py        # HTTP download logic, resume support
│   ├── cookie_store.py      # Cookie management (import/export/set)
│   ├── models.py            # Dataclasses: Album, Track
│   └── utils.py             # Sanitize filenames, slugify, retry decorator
├── tests/
│   ├── conftest.py
│   ├── test_scraper.py
│   ├── test_downloader.py
│   └── fixtures/
│       ├── album_page.html  # Static HTML fixture for unit tests
│       └── track_page.html  # Static HTML fixture for unit tests
├── .github/
│   └── workflows/
│       ├── ci.yml           # Test + lint on push/PR
│       └── publish.yml      # PyPI publish on tag push
├── pyproject.toml
├── README.md
└── .gitignore
```

---

## pyproject.toml (complete)

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pymp3dl"
version = "0.1.0"
description = "Smart MP3 downloader for khinsider.com album pages"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.11"
authors = [{ name = "soulwax", email = "soulwax@users.noreply.github.com" }]
keywords = ["mp3", "downloader", "khinsider", "game-music", "cli"]
classifiers = [
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "License :: OSI Approved :: MIT License",
    "Environment :: Console",
    "Topic :: Multimedia :: Sound/Audio",
]
dependencies = [
    "click>=8.1",
    "httpx>=0.27",            # async-capable HTTP client
    "beautifulsoup4>=4.12",
    "lxml>=5.0",              # fast BS4 parser
    "rich>=13.0",             # progress bars, console output
    "tenacity>=8.2",          # retry logic
    "anyio>=4.0",             # async runtime (used by httpx)
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-httpx>=0.30",
    "ruff>=0.4",
    "mypy>=1.10",
    "types-beautifulsoup4",
]

[project.scripts]
pymp3dl = "pymp3dl.cli:main"

[project.urls]
Homepage = "https://github.com/soulwax/pymp3dl"
Repository = "https://github.com/soulwax/pymp3dl"
Issues = "https://github.com/soulwax/pymp3dl/issues"

[tool.hatch.build.targets.wheel]
packages = ["pymp3dl"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.11"
strict = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## Module Specifications

### `pymp3dl/models.py`

```python
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Track:
    number: int
    title: str
    track_page_url: str          # URL of the khinsider track-detail page
    direct_url: str | None = None  # Real CDN download URL (populated after scraping track page)
    filename: str | None = None    # Sanitized output filename
    size_bytes: int | None = None
    downloaded: bool = False
    skipped: bool = False          # True if file already exists and --no-overwrite

@dataclass
class Album:
    slug: str
    title: str
    url: str
    tracks: list[Track] = field(default_factory=list)
    output_dir: Path = field(default_factory=lambda: Path("."))
```

### `pymp3dl/scraper.py`

Two public coroutines:

```python
async def scrape_album(url: str, client: httpx.AsyncClient) -> Album:
    """
    GET the album page. Parse the track table.
    For each row in the table:
      - Extract track number and title from columns 0 and 1
      - Extract the track_page_url from the 'MP3' column anchor (<a href=...>)
    Returns an Album with tracks populated (direct_url still None).
    
    Selector strategy:
      table = soup.find("table", id="songlist")
      rows  = table.find_all("tr")[1:]  # skip header
      For each row:
        td_list = row.find_all("td")
        number  = td_list[0].text.strip().rstrip(".")
        title   = td_list[1].text.strip()
        mp3_td  = td_list[2]  # "MP3" column (index may vary; verify by header text)
        link    = mp3_td.find("a")["href"]
    """

async def scrape_track_page(track: Track, client: httpx.AsyncClient) -> Track:
    """
    GET the track detail page (track.track_page_url).
    Find the actual CDN download URL.
    
    Selector strategy (in priority order):
      1. audio_tag = soup.find("audio")  → audio_tag["src"]
      2. dl_link   = soup.find("a", class_="songDownloadLink")  → dl_link["href"]
      3. Fallback: find any <a href> ending in ".mp3" that is not on the khinsider domain
    
    Populate track.direct_url and track.filename (sanitized title + ".mp3").
    Return updated Track.
    """
```

### `pymp3dl/downloader.py`

```python
async def download_track(
    track: Track,
    output_dir: Path,
    client: httpx.AsyncClient,
    overwrite: bool = False,
    progress: rich.progress.Progress | None = None,
) -> Track:
    """
    Download track.direct_url → output_dir / track.filename.
    
    - Skip if file exists and not overwrite (set track.skipped = True)
    - Stream response in 8KB chunks, update Rich progress task
    - On HTTP error, raise with clear message including status code and URL
    - Set track.downloaded = True on success
    """

async def download_album(
    album: Album,
    client: httpx.AsyncClient,
    concurrency: int = 3,
    delay: float = 1.5,
    overwrite: bool = False,
) -> Album:
    """
    Scrape all track pages (sequentially with delay to be polite).
    Then download all resolved direct_urls (with concurrency limit via anyio.Semaphore).
    Show a Rich live progress display with:
      - Overall progress bar (tracks done / total)
      - Per-track progress bar while downloading
      - Summary table at the end
    Returns Album with all tracks updated.
    """
```

### `pymp3dl/cookie_store.py`

```python
# Cookies are stored in ~/.config/pymp3dl/cookies.json as a plain dict {name: value}

CONFIG_DIR = Path.home() / ".config" / "pymp3dl"
COOKIE_FILE = CONFIG_DIR / "cookies.json"

def load_cookies() -> dict[str, str]: ...
def save_cookies(cookies: dict[str, str]) -> None: ...
def set_cookie(name: str, value: str) -> None: ...
def delete_cookie(name: str) -> None: ...
def clear_cookies() -> None: ...
def cookies_to_httpx(cookies: dict[str, str]) -> httpx.Cookies: ...
```

### `pymp3dl/cli.py`

```python
import click
from rich.console import Console

console = Console()

@click.group()
@click.version_option()
def main(): ...

@main.command()
@click.argument("url")
@click.option("-o", "--output", default=".", show_default=True,
              help="Output directory. Created if it doesn't exist.")
@click.option("-c", "--concurrency", default=3, show_default=True,
              help="Number of parallel downloads.")
@click.option("--delay", default=1.5, show_default=True,
              help="Seconds between track-page requests (politeness).")
@click.option("--no-overwrite", is_flag=True, default=False,
              help="Skip files that already exist.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Scrape and list tracks without downloading.")
@click.option("--format", "fmt", type=click.Choice(["mp3", "flac"]), default="mp3",
              show_default=True, help="Preferred audio format.")
def download(url, output, concurrency, delay, no_overwrite, dry_run, fmt):
    """Download all tracks from a khinsider album URL."""
    ...

@main.group()
def cookies():
    """Manage stored cookies for authenticated requests."""

@cookies.command("set")
@click.argument("name")
@click.argument("value")
def cookies_set(name, value):
    """Set a cookie by NAME and VALUE.\n\nExample: pymp3dl cookies set khi_session abc123xyz"""
    ...

@cookies.command("list")
def cookies_list():
    """List all stored cookies."""
    ...

@cookies.command("delete")
@click.argument("name")
def cookies_delete(name):
    """Delete a cookie by NAME."""
    ...

@cookies.command("clear")
def cookies_clear():
    """Delete all stored cookies."""
    ...

@cookies.command("import")
@click.argument("file", type=click.Path(exists=True))
@click.option("--format", "fmt", type=click.Choice(["netscape", "json"]),
              default="netscape", show_default=True,
              help="Cookie file format. Use 'netscape' for browser exports.")
def cookies_import(file, fmt):
    """Import cookies from a browser-exported cookie file.\n\nExamples:\n  pymp3dl cookies import ~/cookies.txt --format netscape\n  pymp3dl cookies import ~/cookies.json --format json"""
    ...
```

---

## HTTP Client Setup

The `httpx.AsyncClient` must be initialized with:

```python
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://downloads.khinsider.com/",
}

async with httpx.AsyncClient(
    headers=HEADERS,
    cookies=cookies_to_httpx(load_cookies()),
    follow_redirects=True,
    timeout=httpx.Timeout(30.0, connect=10.0),
) as client:
    ...
```

**Important**: The `Referer` header set to the khinsider domain is often required to avoid 403 responses on the CDN download links.

---

## Retry Logic (`utils.py`)

Use `tenacity`:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(httpx.HTTPError),
    reraise=True,
)
async def fetch_with_retry(client: httpx.AsyncClient, url: str) -> httpx.Response:
    response = await client.get(url)
    response.raise_for_status()
    return response
```

---

## Filename Sanitization (`utils.py`)

```python
import re
from pathlib import Path

def sanitize_filename(name: str) -> str:
    """
    - Strip leading/trailing whitespace
    - Replace characters forbidden on Windows/Linux: \\ / : * ? " < > |
    - Replace multiple spaces/underscores with single space
    - Truncate to 200 chars (safe for all filesystems)
    - Never return empty string (fallback: "track")
    """
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]', "", name)
    name = re.sub(r"\s+", " ", name)
    name = name[:200].strip() or "track"
    return name
```

---

## GitHub Actions: CI (`ci.yml`)

```yaml
name: CI

on:
  push:
    branches: ["main", "develop"]
  pull_request:
    branches: ["main"]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Lint with ruff
        run: ruff check pymp3dl/ tests/

      - name: Type check with mypy
        run: mypy pymp3dl/

      - name: Run tests
        run: pytest tests/ -v --tb=short
```

---

## GitHub Actions: Publish (`publish.yml`)

```yaml
name: Publish to PyPI

on:
  push:
    tags:
      - "v*.*.*"

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write   # Required for trusted publishing (OIDC)

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Build package
        run: |
          pip install hatch
          hatch build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        # Uses OIDC trusted publishing — no API token needed
        # Configure at: https://pypi.org/manage/project/pymp3dl/settings/publishing/
```

**Setup note**: PyPI trusted publishing must be configured at pypi.org. Go to the project's Publishing settings and add a new trusted publisher with `soulwax/pymp3dl`, environment `pypi`, workflow `publish.yml`.

---

## README.md (template)

````markdown
# pymp3dl

Smart MP3 downloader for [khinsider.com](https://downloads.khinsider.com) game soundtrack album pages.

## Features

- Two-step scraping: parses album page → visits each track page → extracts real CDN URL
- Concurrent downloads with politeness delay
- Resume/skip existing files
- Cookie support for authenticated access
- Rich progress display
- Dry-run mode to preview tracklist

## Installation

```bash
pip install pymp3dl
```

Or with [pipx](https://pipx.pypa.io/):

```bash
pipx install pymp3dl
```

## Usage

### Download an album

```bash
pymp3dl download "https://downloads.khinsider.com/game-soundtracks/album/golden-sun-the-lost-age"
```

Save to a specific directory:

```bash
pymp3dl download "https://..." -o ~/Music/GameOST/GoldenSun2
```

Increase concurrency (default: 3):

```bash
pymp3dl download "https://..." -c 5
```

Preview tracks without downloading:

```bash
pymp3dl download "https://..." --dry-run
```

Skip already-downloaded files:

```bash
pymp3dl download "https://..." --no-overwrite
```

### Cookie management

If the site requires login cookies (e.g. for FLAC downloads or rate-limit bypass):

**Set a single cookie** (get value from browser DevTools → Application → Cookies):

```bash
pymp3dl cookies set khi_session "your-session-cookie-value"
```

**Import from a browser cookie export** (e.g. "Get cookies.txt LOCALLY" Chrome extension):

```bash
pymp3dl cookies import ~/Downloads/cookies.txt --format netscape
```

**List stored cookies:**

```bash
pymp3dl cookies list
```

**Delete a cookie:**

```bash
pymp3dl cookies delete khi_session
```

**Clear all cookies:**

```bash
pymp3dl cookies clear
```

### Getting cookies from your browser

1. Log in to `downloads.khinsider.com` in Chrome/Firefox.
2. Open DevTools (F12) → Application tab → Cookies → `https://downloads.khinsider.com`.
3. Find the session cookie (usually named `khi_session` or similar).
4. Copy its value and run:
   ```bash
   pymp3dl cookies set khi_session "PASTE_VALUE_HERE"
   ```

Alternatively, install the [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) extension, export cookies for the site, then use `pymp3dl cookies import`.

## How It Works

khinsider.com uses a two-level indirection system. The album page lists tracks but each "MP3" link points to a **track detail page**, not directly to the audio file. `pymp3dl` visits each track page in turn to extract the real CDN download URL before streaming the file to disk.

## Options Reference

| Option | Default | Description |
|---|---|---|
| `-o, --output` | `.` | Output directory |
| `-c, --concurrency` | `3` | Parallel download count |
| `--delay` | `1.5` | Seconds between track page fetches |
| `--no-overwrite` | off | Skip existing files |
| `--dry-run` | off | List tracks, don't download |
| `--format` | `mp3` | `mp3` or `flac` |

## Contributing

PRs welcome. Run `pip install -e ".[dev]"` then `pytest` before submitting.
````

---

## Implementation Notes for Claude

1. **Scraping the MP3 column index** — do not hardcode column index 2. Instead, read the `<th>` headers and find the one with text "MP3" or "FLAC" to get the correct column index. The table structure can vary.

2. **Track page CDN URL** — test against the live site. The real download link is inside `<p class="songDownloadLink"><a href="...">`. If that changes, fall back to finding any `<a>` whose `href` ends in `.mp3` and whose domain is not `downloads.khinsider.com`.

3. **Output filename strategy** — use zero-padded track number + sanitized title: `f"{track.number:03d} - {sanitize_filename(track.title)}.mp3"` so directories sort correctly.

4. **Async architecture** — `cli.py` calls `anyio.run(...)` (do not use `asyncio.run` directly, as `httpx` recommends anyio). The `download` CLI command is a sync Click command that calls `anyio.run(download_album(...))`.

5. **Error handling** — on 403: print a clear message suggesting the user add cookies. On 429: automatically apply exponential backoff via tenacity. On any scraping failure: log the track as failed and continue with the rest; never abort the whole album run.

6. **Test fixtures** — `tests/fixtures/album_page.html` should be a trimmed copy of the real khinsider album page HTML (with only 3–5 track rows) so tests work offline. `tests/fixtures/track_page.html` should be a single track page with a known CDN URL in it. Use `pytest-httpx` to mock all HTTP calls.

---

## Release Workflow

```bash
# Bump version in pyproject.toml, commit, then:
git tag v0.1.0
git push origin v0.1.0
# → triggers publish.yml → PyPI release
```
