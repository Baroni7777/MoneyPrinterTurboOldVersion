"""Gemini as a fallback for watching candidate clips.

TwelveLabs Pegasus analyses a clip straight from a public URL, which lets the
ranking pipeline discard bad candidates before downloading them. Gemini has no
equivalent: video has to be uploaded through the Files API first. So this module
works on local files, and the caller downloads a candidate before asking about
it.

The trade-off is deliberate — reusing the Gemini key the project already has for
script generation beats having no clip analysis at all when TwelveLabs is not
configured.

Config (config.toml, [app] section):
    gemini_api_key = "..."                     # already used by llm.py
    gemini_video_analysis = true               # required: opt in to this fallback
    gemini_video_model = "gemini-3-flash-preview"   # optional override
"""

from __future__ import annotations

import os
import time

from loguru import logger

from app.config import config

DEFAULT_MODEL = "gemini-3-flash-preview"
# Uploaded video sits in PROCESSING until Gemini has decoded it; generate_content
# fails while it is not ACTIVE.
_PROCESSING_POLL_SECONDS = 2
_PROCESSING_TIMEOUT_SECONDS = 120


def is_enabled() -> bool:
    """True only when a Gemini key exists and the fallback was opted into.

    Kept opt-in because analysing every candidate uploads real video and is
    billed; the project's Gemini key may have been configured only for text.
    """

    if not config.app.get("gemini_video_analysis"):
        return False
    return bool(config.app.get("gemini_api_key"))


def _client():
    from google import genai

    return genai.Client(api_key=config.app.get("gemini_api_key"))


def _model() -> str:
    return config.app.get("gemini_video_model") or DEFAULT_MODEL


def _wait_until_active(client, uploaded):
    deadline = time.monotonic() + _PROCESSING_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        state = getattr(getattr(uploaded, "state", None), "name", None) or getattr(
            uploaded, "state", None
        )
        if state == "ACTIVE":
            return uploaded
        if state == "FAILED":
            raise RuntimeError("Gemini failed to process the uploaded video")
        time.sleep(_PROCESSING_POLL_SECONDS)
        uploaded = client.files.get(name=uploaded.name)
    raise TimeoutError("Gemini did not finish processing the video in time")


def analyze_clip(video_path: str, prompt: str) -> str | None:
    """Ask Gemini about a local video file, returning its text answer or None.

    Never raises: a failed analysis must degrade to "no opinion" so the ranking
    pipeline can fall back to the provider's own ordering.
    """

    if not is_enabled() or not video_path or not os.path.isfile(video_path):
        return None

    client = None
    uploaded = None
    try:
        client = _client()
        uploaded = client.files.upload(file=video_path)
        uploaded = _wait_until_active(client, uploaded)
        response = client.models.generate_content(
            model=_model(), contents=[uploaded, prompt]
        )
        return getattr(response, "text", None)
    except Exception as e:  # noqa: BLE001 - never break the pipeline on Gemini errors
        logger.warning(f"Gemini analyze_clip failed: {e}")
        return None
    finally:
        # The Files API keeps uploads for ~48h and counts against quota; a
        # ranking run uploads several clips, so clean up as we go.
        if client is not None and uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"failed to delete Gemini upload: {e}")
