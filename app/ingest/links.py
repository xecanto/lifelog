import httpx
import trafilatura

from app.ingest.common import create_entry

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; LifelogBot/1.0; personal use)"}


def ingest_link(url: str) -> dict:
    url = url.strip()
    if not url:
        raise ValueError("URL is empty")

    try:
        with httpx.Client(follow_redirects=True, timeout=20.0, headers=_HEADERS) as client:
            resp = client.get(url)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"The page returned an error ({exc.response.status_code})") from exc
    except httpx.HTTPError as exc:
        raise ValueError(f"Could not fetch that URL: {exc}") from exc

    extracted = trafilatura.extract(html, url=url, include_comments=False, include_tables=True) or ""
    metadata = trafilatura.extract_metadata(html, default_url=url)
    title = metadata.title if metadata and metadata.title else url

    if not extracted.strip():
        raise ValueError("Could not extract readable article content from this URL")

    raw_text = f"{title}\n\n{extracted}".strip()

    return create_entry(
        source_type="link",
        raw_text=raw_text,
        source_hint=f"This is the extracted article content from the saved URL: {url}",
        source_url=url,
        metadata={"page_title": title},
    )
