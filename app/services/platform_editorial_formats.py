from __future__ import annotations

from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database.models import EditorialFormat


RANKING_DEFAULTS = {
    "ranking_size": 5,
    "aspect_ratio": "9:16",
    "order": "countdown",
    "title_template": "RANKING BEST {{topic}}",
    "font_family": "Anton",
    "title_color": "#ffffff",
    "accent_color": "#ff3344",
    "secondary_color": "#ffd43b",
    "outline_color": "#000000",
    "title_size": 54,
    "item_size": 42,
    "outline_width": 3,
    "title_position": {"x": 50, "y": 7},
    "ranking_position": {"x": 8, "y": 24},
    "clip_duration": 7,
    "transition": "cut",
    "show_full_ranking": True,
    "show_watermark": False,
    "watermark_text": "",
    "source_audio": True,
}


def normalized_configuration(configuration: dict | None) -> dict:
    result = deepcopy(RANKING_DEFAULTS)
    supplied = deepcopy(configuration or {})
    for nested in ("title_position", "ranking_position"):
        value = supplied.pop(nested, None)
        if isinstance(value, dict):
            result[nested].update(value)
    result.update(supplied)

    result["ranking_size"] = max(2, min(10, int(result["ranking_size"])))
    result["title_size"] = max(20, min(100, int(result["title_size"])))
    result["item_size"] = max(16, min(80, int(result["item_size"])))
    result["outline_width"] = max(0, min(8, int(result["outline_width"])))
    result["clip_duration"] = max(2, min(60, int(result["clip_duration"])))
    for nested in ("title_position", "ranking_position"):
        result[nested]["x"] = max(0, min(100, float(result[nested]["x"])))
        result[nested]["y"] = max(0, min(100, float(result[nested]["y"])))
    return result


def get_format(
    db: Session, project_id: str, format_id: str
) -> EditorialFormat:
    editorial_format = db.get(EditorialFormat, format_id)
    if editorial_format is None or editorial_format.project_id != project_id:
        raise HTTPException(status_code=404, detail="editorial format not found")
    return editorial_format


def get_default_format(
    db: Session, project_id: str
) -> EditorialFormat | None:
    return db.scalar(
        select(EditorialFormat).where(
            EditorialFormat.project_id == project_id,
            EditorialFormat.is_default.is_(True),
        )
    )


def set_default_format(db: Session, project_id: str, format_id: str) -> None:
    db.execute(
        update(EditorialFormat)
        .where(EditorialFormat.project_id == project_id)
        .values(is_default=False)
    )
    editorial_format = db.get(EditorialFormat, format_id)
    if editorial_format:
        editorial_format.is_default = True
