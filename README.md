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

**Set a single cookie** (get value from browser DevTools → Application → Cookies):

```bash
pymp3dl cookies set khi_session "your-session-cookie-value"
```

**Import from a browser cookie export:**

```bash
pymp3dl cookies import ~/Downloads/cookies.txt --format netscape
pymp3dl cookies import ~/Downloads/cookies.json --format json
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

## Options Reference

| Option | Default | Description |
|---|---|---|
| `-o, --output` | `.` | Output directory |
| `-c, --concurrency` | `3` | Parallel download count |
| `--delay` | `1.5` | Seconds between track page fetches |
| `--no-overwrite` | off | Skip existing files |
| `--dry-run` | off | List tracks, don't download |
| `--format` | `mp3` | `mp3` or `flac` |

## How It Works

khinsider.com uses a two-level indirection system. The album page lists tracks but each "MP3" link points to a **track detail page**, not directly to the audio file. `pymp3dl` visits each track page in turn to extract the real CDN download URL before streaming the file to disk.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
ruff check pymp3dl/ tests/
mypy pymp3dl/
```

## Release

```bash
# Bump version in pyproject.toml, commit, then:
git tag v0.1.0
git push origin v0.1.0
# → triggers publish.yml → PyPI release
```

## License

MIT
