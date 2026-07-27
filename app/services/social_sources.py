"""YouTube and TikTok as footage sources for the automatic ranking pipeline.

These sources sit alongside the stock providers in `material.py`, but differ in
two ways that the pipeline has to account for:

  * there is no direct mp4 link in the search result — a watch/page URL has to be
    resolved through yt-dlp, both to download and to hand a fetchable URL to the
    video-understanding model;
  * clips are arbitrarily long (a search can easily return a two-hour film), so
    only the leading seconds actually needed by the renderer are downloaded;
  * YouTube blocks unauthenticated downloads ("Sign in to confirm you're not a
    bot"), so `social_cookies_file` or `social_cookies_from_browser` must be
    configured — searching works without them, downloading does not.

Legal note: YouTube and TikTok terms of service prohibit downloading, and
republishing third-party clips in a compilation is generally copyright
infringement. Enabling these sources is a deliberate choice by the operator.

`yt-dlp` ships with the project but is imported lazily, so a trimmed install
that drops it still runs every other source.
"""

from __future__ import annotations

import os
import re
from typing import List

from loguru import logger

from app.config import config
from app.models.schema import MaterialInfo, VideoAspect

YOUTUBE_PROVIDER = "youtube"
TIKTOK_PROVIDER = "tiktok"
SOCIAL_PROVIDERS = (YOUTUBE_PROVIDER, TIKTOK_PROVIDER)

DEFAULT_SEARCH_RESULTS = 8
# A ranking clip only ever uses its first seconds, so anything feature-length is
# a bad candidate regardless of relevance — and an expensive one to fetch.
DEFAULT_MAX_DURATION = 900
# Extra seconds fetched beyond the configured clip duration, so the renderer has
# room if the cut lands slightly past a keyframe.
DOWNLOAD_TAIL_BUFFER = 4


def is_social_source(source: str) -> bool:
    return (source or "").strip().lower() in SOCIAL_PROVIDERS


def _yt_dlp():
    try:
        import yt_dlp
    except ImportError as exc:  # noqa: TRY003
        raise RuntimeError(
            "yt-dlp is required for the youtube/tiktok sources. "
            "Install it with: pip install yt-dlp"
        ) from exc
    return yt_dlp


def _cookie_options() -> dict:
    """Cookie configuration for platforms that gate downloads behind a login.

    YouTube answers unauthenticated download attempts with "Sign in to confirm
    you're not a bot", so a cookie source is mandatory in practice — searching
    works without it, fetching the media does not.
    """

    options: dict = {}
    cookie_file = str(config.app.get("social_cookies_file", "") or "").strip()
    if cookie_file:
        if os.path.isfile(cookie_file):
            options["cookiefile"] = cookie_file
        else:
            logger.warning(f"social_cookies_file does not exist: {cookie_file}")

    browser = str(config.app.get("social_cookies_from_browser", "") or "").strip()
    if browser and "cookiefile" not in options:
        # yt-dlp takes a tuple of (browser, profile, keyring, container); the
        # config only exposes the browser name, which covers the common case.
        options["cookiesfrombrowser"] = (browser.lower(), None, None, None)
    return options


def _base_options() -> dict:
    options = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "ignoreerrors": True,
    }
    # config.proxy is the requests-style mapping used by the stock providers;
    # yt-dlp takes a single proxy URL instead.
    proxy = (config.proxy or {}).get("https") or (config.proxy or {}).get("http")
    if proxy:
        options["proxy"] = proxy
    options.update(_cookie_options())
    return options


def _max_duration() -> int:
    try:
        return max(30, int(config.app.get("social_max_duration", DEFAULT_MAX_DURATION)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_DURATION


def _search_results() -> int:
    try:
        return max(
            1, min(25, int(config.app.get("social_search_results", DEFAULT_SEARCH_RESULTS)))
        )
    except (TypeError, ValueError):
        return DEFAULT_SEARCH_RESULTS


def _entry_page_url(entry: dict, provider: str) -> str:
    url = entry.get("url") or entry.get("webpage_url") or ""
    if url.startswith("http"):
        return url
    video_id = entry.get("id")
    if not video_id:
        return ""
    if provider == YOUTUBE_PROVIDER:
        return f"https://www.youtube.com/watch?v={video_id}"
    return url


def _collect_entries(query: str, provider: str) -> list[dict]:
    yt_dlp = _yt_dlp()
    options = {
        **_base_options(),
        "skip_download": True,
        # Flat extraction keeps one network round-trip per search instead of one
        # per result; duration/view_count are still present for filtering.
        "extract_flat": True,
        "playlist_items": f"1-{_search_results()}",
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(query, download=False)
    except Exception as exc:  # noqa: BLE001 - a broken extractor must not kill the run
        logger.error(f"{provider} search failed for '{query}': {exc}")
        return []

    entries = (info or {}).get("entries") or []
    return [entry for entry in entries if isinstance(entry, dict)]


def _entries_to_materials(
    entries: list[dict], provider: str, minimum_duration: int
) -> List[MaterialInfo]:
    maximum_duration = _max_duration()
    items: List[MaterialInfo] = []
    for entry in entries:
        page_url = _entry_page_url(entry, provider)
        if not page_url:
            continue
        raw_duration = entry.get("duration")
        # TikTok listings frequently omit duration; those clips are short by
        # construction, so an unknown duration is accepted rather than dropped.
        if raw_duration is None:
            duration = minimum_duration
        else:
            try:
                duration = int(float(raw_duration))
            except (TypeError, ValueError):
                continue
            if duration < minimum_duration or duration > maximum_duration:
                continue

        item = MaterialInfo()
        item.provider = provider
        item.url = page_url
        item.duration = duration
        items.append(item)
    return items


def search_videos_youtube(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    """Keyword search on YouTube.

    `video_aspect` is accepted for signature parity with the stock providers but
    is not filtered on: flat search results carry no dimensions, and the ranking
    renderer crops every clip to portrait anyway.
    """

    query = f"ytsearch{_search_results()}:{search_term}"
    logger.info(f"searching youtube: {search_term}")
    entries = _collect_entries(query, YOUTUBE_PROVIDER)
    items = _entries_to_materials(entries, YOUTUBE_PROVIDER, minimum_duration)
    logger.info(f"found {len(items)} youtube videos for '{search_term}'")
    return items


def _hashtag(search_term: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", (search_term or "").lower())


def search_videos_tiktok(
    search_term: str,
    minimum_duration: int,
    video_aspect: VideoAspect = VideoAspect.portrait,
) -> List[MaterialInfo]:
    """Hashtag search on TikTok.

    TikTok has no public keyword-search API and yt-dlp exposes no search
    extractor for it, so the search term is reduced to a hashtag feed. Note that
    yt-dlp currently marks its TikTok extractors as broken upstream; this
    returns an empty list in that case so the caller can fall back to another
    source rather than failing the whole generation.
    """

    tag = _hashtag(search_term)
    if not tag:
        logger.warning(f"'{search_term}' has no usable tiktok hashtag")
        return []

    logger.info(f"searching tiktok hashtag: #{tag}")
    entries = _collect_entries(f"https://www.tiktok.com/tag/{tag}", TIKTOK_PROVIDER)
    items = _entries_to_materials(entries, TIKTOK_PROVIDER, minimum_duration)
    if not items:
        logger.warning(
            f"no usable tiktok results for #{tag}; yt-dlp's tiktok extractor is "
            "known to break when the site changes"
        )
    logger.info(f"found {len(items)} tiktok videos for '{search_term}'")
    return items


def resolve_stream_url(page_url: str) -> str | None:
    """Return a directly fetchable media URL for `page_url`, or None.

    Used to let the video-understanding model watch a candidate *before* it is
    downloaded, mirroring how the stock providers hand over an mp4 link. A
    progressive format (muxed audio+video) is required, since a single URL has
    to carry the whole clip.
    """

    yt_dlp = _yt_dlp()
    options = {
        **_base_options(),
        "skip_download": True,
        "format": "best[ext=mp4][acodec!=none][vcodec!=none]/best[acodec!=none][vcodec!=none]",
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(page_url, download=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"failed to resolve stream url for {page_url}: {exc}")
        return None

    if not info:
        return None
    url = info.get("url")
    if url:
        return url
    for candidate in reversed(info.get("formats") or []):
        if candidate.get("acodec") not in (None, "none") and candidate.get(
            "vcodec"
        ) not in (None, "none"):
            return candidate.get("url")
    return None


def download_video(page_url: str, save_dir: str, seconds: int = 0) -> str:
    """Download `page_url` into `save_dir`, returning the file path or "".

    Only the leading `seconds` are fetched when given, which keeps a two-hour
    search hit from becoming a two-hour download for a seven-second slot.
    """

    yt_dlp = _yt_dlp()
    os.makedirs(save_dir, exist_ok=True)
    options = {
        **_base_options(),
        "outtmpl": os.path.join(save_dir, "social-%(id)s.%(ext)s"),
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "merge_output_format": "mp4",
        "ignoreerrors": False,
    }
    if seconds > 0:
        options["download_ranges"] = yt_dlp.utils.download_range_func(
            None, [(0, seconds + DOWNLOAD_TAIL_BUFFER)]
        )
        options["force_keyframes_at_cuts"] = True

    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(page_url, download=True)
            if not info:
                return ""
            path = downloader.prepare_filename(info)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"failed to download {page_url}: {exc}")
        return ""

    if os.path.isfile(path) and os.path.getsize(path) > 0:
        return path
    # merge_output_format rewrites the extension after prepare_filename ran.
    merged = f"{os.path.splitext(path)[0]}.mp4"
    if os.path.isfile(merged) and os.path.getsize(merged) > 0:
        return merged
    logger.error(f"download produced no usable file for {page_url}")
    return ""
