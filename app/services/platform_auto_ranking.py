"""Automatic top-N ranking videos.

Turns a single theme into a finished ranking video without any manual upload:

  1. the LLM plans the ranking (position, title and a stock search term per item);
  2. each item is searched on the configured stock provider (pexels/pixabay/coverr);
  3. the AI picks which candidate clip actually depicts the item;
  4. the winning clips are downloaded, registered as assets and handed to the
     existing ranking renderer in `platform_ranking`.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re

from loguru import logger
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.database.models import Asset, Generation
from app.models.schema import MaterialInfo, VideoAspect
from app.services import llm, material, social_sources, twelvelabs
from app.services.platform_ranking import RankingStageError
from app.utils import utils

# How many stock candidates per ranking item are considered by the AI picker.
# Analyzing every search hit would multiply cost and latency for little gain.
MAX_CANDIDATES_PER_ITEM = 4
DEFAULT_SEARCH_SOURCE = "pexels"
DEFAULT_MIN_CLIP_DURATION = 5


def build_plan_prompt(video_subject: str, ranking_size: int, language: str) -> str:
    return f"""
# Role: Ranking Video Planner

## Goals:
Plan a top-{ranking_size} ranking video about the subject below.

## Constrains:
1. return a json-array with exactly {ranking_size} objects, nothing else.
2. each object has the keys "position", "title" and "search_term".
3. "position" is an integer from 1 to {ranking_size}, each used exactly once.
4. "title" is the name of the ranked item, written in {language}, max 60 characters.
5. "search_term" is an english stock-footage search query of 1-4 words that
   visually represents that item. never reply with a non-english search term.
6. the items must be real, distinct and genuinely related to the subject.

## Output Example:
[{{"position": 1, "title": "Exemplo", "search_term": "example footage"}}]

## Context:
### Video Subject
{video_subject}
""".strip()


def _coerce_plan(payload, ranking_size: int) -> list[dict]:
    if not isinstance(payload, list):
        raise ValueError("ranking plan is not a json array")

    items: list[dict] = []
    seen_positions: set[int] = set()
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        search_term = str(entry.get("search_term") or "").strip()
        if not title or not search_term:
            continue
        try:
            position = int(entry.get("position"))
        except (TypeError, ValueError):
            continue
        if position < 1 or position in seen_positions:
            continue
        seen_positions.add(position)
        items.append(
            {"position": position, "title": title[:160], "search_term": search_term}
        )

    items.sort(key=lambda item: item["position"])
    return items[:ranking_size]


def plan_ranking_items(
    video_subject: str, ranking_size: int, language: str = "pt-BR"
) -> list[dict]:
    """Ask the LLM for the ranked items and their stock search terms."""

    prompt = build_plan_prompt(video_subject, ranking_size, language)
    response = llm._generate_response(prompt)
    if not response or response.startswith("Error: "):
        raise RankingStageError("ranking_plan", f"failed to plan ranking: {response}")

    text = llm._strip_code_fence(response)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*]", text, re.DOTALL)
        if not match:
            raise RankingStageError(
                "ranking_plan", "ranking plan response is not valid json"
            ) from None
        try:
            payload = json.loads(match.group())
        except json.JSONDecodeError as exc:
            raise RankingStageError(
                "ranking_plan", f"ranking plan response is not valid json: {exc}"
            ) from exc

    items = _coerce_plan(payload, ranking_size)
    if len(items) < 2:
        raise RankingStageError(
            "ranking_plan", "ranking plan needs at least two usable items"
        )
    logger.success(f"planned ranking: {[item['title'] for item in items]}")
    return items


def _search_candidates(
    search_term: str,
    source: str,
    video_aspect: VideoAspect,
    minimum_duration: int,
) -> list[MaterialInfo]:
    search_videos = material.search_videos_pexels
    if source == "pixabay":
        search_videos = material.search_videos_pixabay
    elif source == "coverr":
        search_videos = material.search_videos_coverr
    elif source == social_sources.YOUTUBE_PROVIDER:
        search_videos = social_sources.search_videos_youtube
    elif source == social_sources.TIKTOK_PROVIDER:
        search_videos = social_sources.search_videos_tiktok
    return search_videos(
        search_term=search_term,
        minimum_duration=minimum_duration,
        video_aspect=video_aspect,
    )


def _parse_score(answer: str | None) -> float | None:
    if not answer:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", answer)
    if not match:
        return None
    try:
        score = float(match.group().replace(",", "."))
    except ValueError:
        return None
    return max(0.0, min(10.0, score))


def _analysis_url(candidate: MaterialInfo) -> str | None:
    """URL the video-understanding model can actually fetch.

    Stock providers hand over a direct mp4. YouTube/TikTok hand over a watch
    page, which has to be resolved to a media URL first.
    """

    if social_sources.is_social_source(candidate.provider):
        return social_sources.resolve_stream_url(candidate.url)
    return candidate.url


def choose_clip(
    video_subject: str, item_title: str, candidates: list[MaterialInfo]
) -> MaterialInfo | None:
    """Pick the candidate that best depicts `item_title`.

    Uses TwelveLabs Pegasus to actually watch each candidate when it is
    configured; otherwise falls back to the provider's own ranking (first hit),
    so the pipeline still works without the optional integration.
    """

    if not candidates:
        return None
    if not twelvelabs.is_enabled():
        return candidates[0]

    prompt = (
        f'Rate from 0 to 10 how well this video visually represents "{item_title}" '
        f'in a ranking video about "{video_subject}". Reply with the number only.'
    )
    best: tuple[float, MaterialInfo] | None = None
    for candidate in candidates[:MAX_CANDIDATES_PER_ITEM]:
        analysis_url = _analysis_url(candidate)
        if not analysis_url:
            continue
        score = _parse_score(twelvelabs.analyze_clip(analysis_url, prompt=prompt))
        if score is None:
            continue
        logger.info(f"clip score {score} for '{item_title}': {candidate.url}")
        if best is None or score > best[0]:
            best = (score, candidate)

    if best is None:
        logger.warning(
            f"no clip could be analyzed for '{item_title}', using the first candidate"
        )
        return candidates[0]
    return best[1]


def _download_candidate(
    candidate: MaterialInfo, save_dir: str, clip_duration: int
) -> str:
    if social_sources.is_social_source(candidate.provider):
        return social_sources.download_video(
            candidate.url, save_dir=save_dir, seconds=clip_duration
        )
    return material.save_video(video_url=candidate.url, save_dir=save_dir)


def _register_asset(
    db: Session, generation: Generation, path: str, provider: str
) -> Asset:
    storage_key = os.path.relpath(path, utils.task_dir()).replace("\\", "/")
    asset = Asset(
        workspace_id=generation.workspace_id,
        project_id=generation.project_id,
        generation_id=generation.id,
        kind="source_video",
        storage_key=storage_key,
        original_filename=os.path.basename(path),
        mime_type=mimetypes.guess_type(path)[0] or "video/mp4",
        size_bytes=os.path.getsize(path),
        source_provider=provider,
    )
    db.add(asset)
    db.flush()
    return asset


def prepare_auto_ranking_items(
    db: Session, generation: Generation, task_id: str
) -> None:
    """Fill `editorial_format_snapshot["ranking_items"]` from the theme alone."""

    snapshot = generation.editorial_format_snapshot
    configuration = snapshot["configuration"]
    resolved = generation.resolved_configuration or {}

    ranking_size = int(configuration["ranking_size"])
    source = (resolved.get("video_source") or DEFAULT_SEARCH_SOURCE).strip().lower()
    video_aspect = VideoAspect(
        resolved.get("video_aspect") or VideoAspect.portrait.value
    )
    clip_duration = int(configuration["clip_duration"])
    minimum_duration = max(DEFAULT_MIN_CLIP_DURATION, clip_duration)
    language = resolved.get("video_language") or "pt-BR"

    plan = plan_ranking_items(generation.video_subject, ranking_size, language)
    download_dir = utils.task_dir(task_id)

    ranking_items: list[dict] = []
    used_urls: set[str] = set()
    for item in plan:
        candidates = [
            candidate
            for candidate in _search_candidates(
                item["search_term"], source, video_aspect, minimum_duration
            )
            if candidate.url not in used_urls
        ]
        chosen = choose_clip(generation.video_subject, item["title"], candidates)
        if chosen is None:
            logger.warning(
                f"no stock footage found for '{item['title']}' "
                f"(term: {item['search_term']}), skipping it"
            )
            continue

        used_urls.add(chosen.url)
        path = _download_candidate(chosen, download_dir, clip_duration)
        if not path:
            logger.warning(f"failed to download footage for '{item['title']}'")
            continue

        asset = _register_asset(db, generation, path, chosen.provider or source)
        ranking_items.append(
            {
                "position": item["position"],
                "title": item["title"],
                "asset_id": asset.id,
                "search_term": item["search_term"],
                "source_url": chosen.url,
            }
        )

    if len(ranking_items) < 2:
        raise RankingStageError(
            "ranking_materials",
            "could not collect footage for at least two ranking items",
        )

    # Positions must stay contiguous: skipped items would otherwise leave gaps
    # like 1, 2, 4 in the on-screen ranking.
    for position, entry in enumerate(
        sorted(ranking_items, key=lambda value: value["position"]), start=1
    ):
        entry["position"] = position

    snapshot["ranking_items"] = ranking_items
    flag_modified(generation, "editorial_format_snapshot")
    db.flush()


def execute_auto_ranking_generation(generation_id: str, task_id: str) -> dict:
    from app.services import platform_ranking

    return platform_ranking.execute_ranking_generation(
        generation_id=generation_id,
        task_id=task_id,
        prepare=prepare_auto_ranking_items,
    )
