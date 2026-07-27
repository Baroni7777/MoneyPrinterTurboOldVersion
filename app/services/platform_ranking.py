from __future__ import annotations

import os
from datetime import datetime, timezone

from loguru import logger
from moviepy import (
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
    vfx,
)

from app.database.models import Asset, Generation
from app.database.session import SessionLocal
from app.models import const
from app.services import state as sm
from app.utils import file_security, utils

VIDEO_SIZE = (720, 1280)
VIDEO_FPS = 30


class RankingStageError(Exception):
    """Failure that knows which pipeline stage it belongs to."""

    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage


def _font_path(_family: str) -> str:
    preferred = utils.font_dir("BeVietnamPro-Bold.ttf")
    return preferred if os.path.isfile(preferred) else utils.font_dir("MicrosoftYaHeiBold.ttc")


def _fit_vertical(clip: VideoFileClip):
    target_width, target_height = VIDEO_SIZE
    source_ratio = clip.w / clip.h
    target_ratio = target_width / target_height
    if source_ratio > target_ratio:
        resized = clip.resized(height=target_height)
        return resized.cropped(
            x_center=resized.w / 2,
            width=target_width,
            height=target_height,
        )
    resized = clip.resized(width=target_width)
    return resized.cropped(
        y_center=resized.h / 2,
        width=target_width,
        height=target_height,
    )


def _text_clip(
    text: str,
    *,
    font: str,
    size: int,
    color: str,
    outline: str,
    outline_width: int,
    width: int,
):
    return TextClip(
        font=font,
        text=text,
        font_size=size,
        color=color,
        stroke_color=outline,
        stroke_width=outline_width,
        method="caption",
        size=(width, None),
        text_align="left",
    )


def _position(clip, point: dict, *, center_x: bool = False):
    x = int(VIDEO_SIZE[0] * float(point.get("x", 0)) / 100)
    y = int(VIDEO_SIZE[1] * float(point.get("y", 0)) / 100)
    if center_x:
        x -= int(clip.w / 2)
    return clip.with_position((x, y))


def render_ranking(
    generation: Generation,
    source_assets: dict[str, Asset],
    output_path: str,
) -> None:
    snapshot = generation.editorial_format_snapshot
    configuration = snapshot["configuration"]
    items = snapshot["ranking_items"]
    if len(items) < 2:
        raise ValueError("ranking requires at least two video items")

    font = _font_path(configuration.get("font_family", ""))
    duration = int(configuration["clip_duration"])
    clips = []
    opened = []
    try:
        for item in items:
            asset = source_assets[item["asset_id"]]
            path = file_security.resolve_path_within_directory(
                utils.task_dir(), asset.storage_key
            )
            source = VideoFileClip(path, audio=bool(configuration["source_audio"]))
            opened.append(source)
            usable_duration = min(float(source.duration), duration)
            if usable_duration <= 0:
                raise ValueError(f"empty video: {asset.original_filename}")
            clip = _fit_vertical(source.subclipped(0, usable_duration))
            transition = configuration.get("transition", "cut")
            if transition == "fade":
                clip = clip.with_effects([vfx.FadeIn(0.3)])
            elif transition == "zoom":
                clip = clip.resized(
                    lambda time: 1 + (0.04 * time / usable_duration)
                ).with_position("center")

            title = configuration["title_template"].replace(
                "{{topic}}", generation.video_subject.upper()
            )
            title_layer = _text_clip(
                title,
                font=font,
                size=int(configuration["title_size"]),
                color=configuration["title_color"],
                outline=configuration["outline_color"],
                outline_width=int(configuration["outline_width"]),
                width=650,
            )
            title_layer = _position(
                title_layer,
                configuration["title_position"],
                center_x=True,
            ).with_duration(usable_duration)

            ordered = sorted(
                items,
                key=lambda value: value["position"],
                reverse=configuration["order"] == "countdown",
            )
            if not configuration.get("show_full_ranking", True):
                ordered = [
                    ranked_item
                    for ranked_item in ordered
                    if ranked_item["position"] == item["position"]
                ]
            ranking_layers = []
            base_position = configuration["ranking_position"]
            line_step = max(34, int(configuration["item_size"] * 1.25))
            for line_index, ranked_item in enumerate(ordered):
                label = f'{ranked_item["position"]}.'
                if ranked_item["position"] == item["position"]:
                    label += f' {ranked_item["title"]}'
                active = ranked_item["position"] == item["position"]
                line_color = (
                    configuration["accent_color"]
                    if active
                    else (
                        configuration["secondary_color"]
                        if line_index % 2 == 0
                        else configuration["title_color"]
                    )
                )
                ranking_layer = _text_clip(
                    label,
                    font=font,
                    size=int(configuration["item_size"]),
                    color=line_color,
                    outline=configuration["outline_color"],
                    outline_width=int(configuration["outline_width"]),
                    width=600,
                )
                line_position = {
                    "x": base_position["x"],
                    "y": float(base_position["y"])
                    + (line_index * line_step / VIDEO_SIZE[1] * 100),
                }
                ranking_layers.append(
                    _position(ranking_layer, line_position).with_duration(
                        usable_duration
                    )
                )

            layers = [clip, title_layer, *ranking_layers]
            if configuration.get("show_watermark"):
                watermark = _text_clip(
                    configuration.get("watermark_text") or "@canal",
                    font=font,
                    size=24,
                    color="#ffffff",
                    outline="#000000",
                    outline_width=1,
                    width=300,
                ).with_position(("right", "bottom")).with_duration(usable_duration)
                layers.append(watermark)
            clips.append(
                CompositeVideoClip(layers, size=VIDEO_SIZE).with_duration(
                    usable_duration
                )
            )

        final = concatenate_videoclips(clips, method="compose")
        final.write_videofile(
            output_path,
            fps=VIDEO_FPS,
            codec="libx264",
            audio_codec="aac",
            audio_bitrate="192k",
            threads=4,
            logger=None,
        )
        final.close()
    finally:
        for clip in clips:
            clip.close()
        for source in opened:
            source.close()


def execute_ranking_generation(
    generation_id: str, task_id: str, prepare=None
) -> dict:
    """Render a ranking generation.

    `prepare` is an optional hook that fills in the snapshot's ranking items
    before rendering — used by the automatic pipeline, which sources and
    downloads its own footage instead of relying on uploaded assets.
    """

    with SessionLocal() as db:
        generation = db.get(Generation, generation_id)
        if generation is None:
            return {"error": "generation not found"}
        generation.status = "processing"
        generation.started_at = datetime.now(timezone.utc)
        db.commit()
        try:
            if prepare is not None:
                prepare(db, generation, task_id)
            item_ids = {
                item["asset_id"]
                for item in generation.editorial_format_snapshot["ranking_items"]
                if item.get("asset_id")
            }
            assets = {
                asset_id: db.get(Asset, asset_id) for asset_id in item_ids
            }
            if any(
                asset is None or asset.project_id != generation.project_id
                for asset in assets.values()
            ):
                raise ValueError("one or more ranking assets are invalid")
            output_dir = utils.task_dir(task_id)
            output_path = os.path.join(output_dir, "ranking-final.mp4")
            render_ranking(generation, assets, output_path)
            storage_key = os.path.relpath(
                output_path, utils.task_dir()
            ).replace("\\", "/")
            output_asset = Asset(
                workspace_id=generation.workspace_id,
                project_id=generation.project_id,
                generation_id=generation.id,
                kind="combined_video",
                storage_key=storage_key,
                original_filename="ranking-final.mp4",
                mime_type="video/mp4",
                size_bytes=os.path.getsize(output_path),
                source_provider="ranking_renderer",
            )
            db.add(output_asset)
            generation.status = "completed"
            generation.completed_at = datetime.now(timezone.utc)
            sm.state.update_task(
                task_id,
                state=const.TASK_STATE_COMPLETE,
                progress=100,
                videos=[output_path],
                combined_videos=[output_path],
            )
            db.commit()
            return {"video": output_path}
        except Exception as exc:
            logger.exception(f"ranking render failed: {exc}")
            stage = getattr(exc, "stage", "ranking")
            # The prepare hook may have added rows before failing; drop them so a
            # failed generation never leaves half-built ranking state behind.
            db.rollback()
            generation = db.get(Generation, generation_id)
            generation.status = "failed"
            generation.error_stage = stage
            generation.error_message = str(exc)
            generation.completed_at = datetime.now(timezone.utc)
            sm.state.update_task(
                task_id,
                state=const.TASK_STATE_FAILED,
                progress=0,
                failed_stage=stage,
                error=str(exc),
            )
            db.commit()
            return {"error": str(exc)}
