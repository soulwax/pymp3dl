import re

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


def sanitize_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]', "", name)
    name = re.sub(r"\s+", " ", name)
    name = name[:200].strip() or "track"
    return name


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
