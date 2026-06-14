from pathlib import Path

import anyio
import click
import httpx
from rich.console import Console

from . import __version__
from .cookie_store import (
    clear_cookies,
    cookies_to_httpx,
    delete_cookie,
    import_json_cookies,
    import_netscape_cookies,
    load_cookies,
    set_cookie,
)
from .downloader import download_album
from .scraper import scrape_album

console = Console()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://downloads.khinsider.com/",
}


@click.group()
@click.version_option(__version__)
def main() -> None:
    """pymp3dl — Smart MP3 downloader for khinsider.com."""


@main.command()
@click.argument("url")
@click.option("-o", "--output", default=".", show_default=True, help="Output directory.")
@click.option("-c", "--concurrency", default=3, show_default=True, help="Parallel downloads.")
@click.option("--delay", default=1.5, show_default=True, help="Seconds between track-page fetches.")
@click.option("--no-overwrite", is_flag=True, default=False, help="Skip existing files.")
@click.option("--dry-run", is_flag=True, default=False, help="List tracks without downloading.")
@click.option(
    "--format", "fmt",
    type=click.Choice(["mp3", "flac"]),
    default="mp3",
    show_default=True,
    help="Preferred audio format.",
)
def download(
    url: str,
    output: str,
    concurrency: int,
    delay: float,
    no_overwrite: bool,
    dry_run: bool,
    fmt: str,
) -> None:
    """Download all tracks from a khinsider album URL."""

    async def _run() -> None:
        async with httpx.AsyncClient(
            headers=HEADERS,
            cookies=cookies_to_httpx(load_cookies()),
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, connect=10.0),
        ) as client:
            album = await scrape_album(url, client, fmt=fmt)
            album.output_dir = Path(output)

            if dry_run:
                console.print(f"[bold]{album.title}[/bold] — {len(album.tracks)} tracks")
                for track in album.tracks:
                    console.print(f"  {track.number:03d}  {track.title}")
                return

            await download_album(
                album,
                client,
                concurrency=concurrency,
                delay=delay,
                overwrite=not no_overwrite,
                fmt=fmt,
            )

    anyio.run(_run)


@main.group()
def cookies() -> None:
    """Manage stored cookies for authenticated requests."""


@cookies.command("set")
@click.argument("name")
@click.argument("value")
def cookies_set(name: str, value: str) -> None:
    """Set a cookie by NAME and VALUE."""
    set_cookie(name, value)
    console.print(f"[green]Cookie '{name}' saved.[/green]")


@cookies.command("list")
def cookies_list() -> None:
    """List all stored cookies."""
    stored = load_cookies()
    if not stored:
        console.print("[yellow]No cookies stored.[/yellow]")
        return
    for name, value in stored.items():
        masked = value[:4] + "…" if len(value) > 4 else value
        console.print(f"  {name} = {masked}")


@cookies.command("delete")
@click.argument("name")
def cookies_delete(name: str) -> None:
    """Delete a cookie by NAME."""
    delete_cookie(name)
    console.print(f"[green]Cookie '{name}' deleted.[/green]")


@cookies.command("clear")
def cookies_clear() -> None:
    """Delete all stored cookies."""
    clear_cookies()
    console.print("[green]All cookies cleared.[/green]")


@cookies.command("import")
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--format", "fmt",
    type=click.Choice(["netscape", "json"]),
    default="netscape",
    show_default=True,
    help="Cookie file format.",
)
def cookies_import(file: str, fmt: str) -> None:
    """Import cookies from a browser-exported cookie file."""
    if fmt == "netscape":
        import_netscape_cookies(file)
    else:
        import_json_cookies(file)
    console.print(f"[green]Cookies imported from {file}.[/green]")
