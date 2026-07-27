from copy import deepcopy

from app.models.schema import VideoParams

ALLOWED_OVERRIDES = set(VideoParams.model_fields) - {
    "video_subject", "video_script", "video_terms", "video_materials"
}


def _style_prompt(profile_config: dict, narrative_structure: str) -> str:
    editorial = profile_config.get("editorial", {})
    tone = editorial.get("tone", "casual e claro")
    audience = editorial.get("target_audience", "público geral")
    forbidden = ", ".join(editorial.get("forbidden_phrases", []))
    structure = narrative_structure if narrative_structure != "auto" else "a estrutura mais adequada"
    return (
        f"Escreva em tom {tone}, para {audience}. Use {structure}. "
        "Entregue uma perspectiva original, um exemplo concreto e uma conclusão específica. "
        "Evite urgência artificial, clichês e afirmações não verificadas."
        + (f" Não use: {forbidden}." if forbidden else "")
    )


def resolve_video_params(
    *, profile_config: dict, preset_config: dict, subject: str,
    narrative_structure: str, paragraph_number: int, overrides: dict,
) -> VideoParams:
    values: dict = {"video_subject": subject, "paragraph_number": paragraph_number}
    values.update(deepcopy(profile_config.get("video", {})))
    values.update(deepcopy(preset_config))
    values.update({key: value for key, value in overrides.items() if key in ALLOWED_OVERRIDES})
    visual = profile_config.get("visual", {})
    values["match_materials_to_script"] = bool(
        visual.get("match_materials_to_script", True)
    )
    if values["match_materials_to_script"]:
        values["video_concat_mode"] = "sequential"
    values["video_script_prompt"] = _style_prompt(profile_config, narrative_structure)
    return VideoParams.model_validate(values)


def build_scene_plan(video_script: str, terms: list[str]) -> dict:
    paragraphs = [part.strip() for part in video_script.split("\n\n") if part.strip()]
    scenes = []
    for index, narration in enumerate(paragraphs or [video_script.strip()]):
        if not narration:
            continue
        term = terms[index] if index < len(terms) else (terms[-1] if terms else "")
        scenes.append({
            "index": index + 1,
            "narration": narration,
            "search_terms": [term] if term else [],
            "purpose": "narrative progression",
        })
    return {"scenes": scenes}
