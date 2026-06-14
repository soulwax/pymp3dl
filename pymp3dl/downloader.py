from pathlib import Path

import anyio
import httpx
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from .models import Album, Track
from .scraper import scrape_track_page

_CHUNK = 8192
console = Console()


async def download_track(
    track: Track,
    output_dir: Path,
    client: httpx.AsyncClient,
    overwrite: bool = False,
    progress: Progress | None = None,
    task_id: TaskID | None = None,
) -> Track:
    assert track.direct_url is not None, "direct_url must be resolved before downloading"
    assert track.filename is not None

    dest = output_dir / track.filename

    if dest.exists() and not overwrite:
        track.skipped = True
        return track

    output_dir.mkdir(parents=True, exist_ok=True)

    async with client.stream("GET", track.direct_url) as response:
        if response.status_code == 403:
            raise RuntimeError(
                f"HTTP 403 for {track.direct_url} — try adding session cookies with "
                "'pymp3dl cookies set <name> <value>'"
            )
        response.raise_for_status()

        total = int(response.headers.get("content-length", 0)) or None
        if progress is not None and task_id is not None and total:
            progress.update(task_id, total=total)

        with dest.open("wb") as fh:
            async for chunk in response.aiter_bytes(_CHUNK):
                fh.write(chunk)
                if progress is not None and task_id is not None:
                    progress.advance(task_id, len(chunk))

    track.size_bytes = dest.stat().st_size
    track.downloaded = True
    return track


async def download_album(
    album: Album,
    client: httpx.AsyncClient,
    concurrency: int = 3,
    delay: float = 1.5,
    overwrite: bool = False,
    fmt: str = "mp3",
) -> Album:
    # Phase 1: scrape all track pages sequentially with polite delay
    console.print(
        f"[bold]Scraping {len(album.tracks)} track pages for:[/bold] {album.title} "
        f"[dim](~{len(album.tracks) * delay:.0f}s)[/dim]"
    )
    failed_scrape: list[Track] = []
    for i, track in enumerate(album.tracks):
        try:
            await scrape_track_page(track, client, fmt=fmt)
            console.print(f"  [{i + 1}/{len(album.tracks)}] {track.title}")
        except Exception as exc:  # noqa: BLE001
            console.print(f"  [red]FAILED[/red] {track.title}: {exc}")
            failed_scrape.append(track)
        if i < len(album.tracks) - 1:
            await anyio.sleep(delay)

    resolved = [t for t in album.tracks if t.direct_url is not None]
    console.print(f"\n[bold]Downloading {len(resolved)} tracks…[/bold]")

    # Phase 2: download concurrently
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        overall = progress.add_task("Overall", total=len(resolved))
        semaphore = anyio.Semaphore(concurrency)
        failed_dl: list[tuple[Track, Exception]] = []

        async def _dl(track: Track) -> None:
            task_id = progress.add_task(
                f"[cyan]{track.filename}[/cyan]", total=None, start=False
            )
            progress.start_task(task_id)
            async with semaphore:
                try:
                    await download_track(
                        track, album.output_dir, client, overwrite, progress, task_id
                    )
                except Exception as exc:  # noqa: BLE001
                    failed_dl.append((track, exc))
                finally:
                    progress.advance(overall, 1)
                    progress.remove_task(task_id)

        async with anyio.create_task_group() as tg:
            for track in resolved:
                tg.start_soon(_dl, track)

    # Summary
    table = Table(title="Download Summary", show_lines=True)
    table.add_column("#", style="dim")
    table.add_column("Title")
    table.add_column("Status")
    for track in album.tracks:
        if track.downloaded:
            status = "[green]downloaded[/green]"
        elif track.skipped:
            status = "[yellow]skipped[/yellow]"
        elif track in failed_scrape:
            status = "[red]scrape failed[/red]"
        else:
            match = next((e for t, e in failed_dl if t is track), None)
            status = f"[red]dl failed: {match}[/red]" if match else "[red]failed[/red]"
        table.add_row(str(track.number), track.title, status)
    console.print(table)

    return album
