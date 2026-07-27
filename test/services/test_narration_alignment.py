"""Clip cuts must land on narration boundaries instead of a fixed interval."""

import pytest

from app.services import subtitle, task, video, voice


def test_plan_packs_segments_without_exceeding_the_cap():
    # 2s + 2s fit in one 5s slot; adding the third would exceed it.
    segments = [(0, 2), (2, 4), (4, 7), (7, 8)]

    plan = video.plan_clip_durations(segments, max_clip_duration=5)

    assert plan == [4.0, 4.0]
    assert sum(plan) == 8.0


def test_plan_boundaries_always_coincide_with_segment_ends():
    segments = [(0, 1.5), (1.5, 4.0), (4.0, 4.5), (4.5, 9.0)]

    plan = video.plan_clip_durations(segments, max_clip_duration=5)

    boundaries = []
    running = 0.0
    for slot in plan:
        running += slot
        boundaries.append(round(running, 6))
    segment_ends = {round(end, 6) for _, end in segments}
    assert set(boundaries).issubset(segment_ends)


def test_plan_splits_a_segment_longer_than_the_cap():
    plan = video.plan_clip_durations([(0, 12)], max_clip_duration=5)

    # 12s cannot fit under a 5s cap, so it becomes three equal 4s slots that
    # still finish exactly where the sentence ends.
    assert plan == [4.0, 4.0, 4.0]
    assert max(plan) <= 5


def test_plan_flushes_pending_before_splitting_a_long_segment():
    plan = video.plan_clip_durations([(0, 3), (3, 15)], max_clip_duration=5)

    assert plan[0] == 3.0
    assert sum(plan) == 15.0
    assert all(slot <= 5 for slot in plan)


def test_plan_total_matches_narration_duration():
    segments = [(0, 1.2), (1.2, 6.9), (6.9, 8.1), (8.1, 13.4)]

    plan = video.plan_clip_durations(segments, max_clip_duration=5)

    assert sum(plan) == pytest.approx(13.4)


def test_plan_ignores_empty_and_inverted_segments():
    plan = video.plan_clip_durations([(0, 0), (5, 3), (0, 2)], max_clip_duration=5)

    assert plan == [2.0]


def test_plan_is_empty_without_segments():
    assert video.plan_clip_durations([], max_clip_duration=5) == []


def _material_metadata(monkeypatch, durations):
    monkeypatch.setattr(
        video,
        "_read_material_metadata",
        lambda paths: [
            (path, durations[index], 1080, 1920) for index, path in enumerate(paths)
        ],
    )


def test_subclips_fill_each_slot_exactly(monkeypatch):
    _material_metadata(monkeypatch, [10.0, 10.0])

    items = video.plan_subclips_for_narration(["a.mp4", "b.mp4"], [4.0, 3.0])

    assert [round(item.duration, 6) for item in items] == [4.0, 3.0]
    assert items[0].file_path == "a.mp4"
    # The second slot continues in the same material, from where the first ended.
    assert items[1].start_time == pytest.approx(4.0)


def test_short_material_is_completed_by_the_next_one(monkeypatch):
    _material_metadata(monkeypatch, [2.0, 10.0])

    items = video.plan_subclips_for_narration(["a.mp4", "b.mp4"], [5.0])

    # The slot still adds up to its full narration duration.
    assert sum(item.duration for item in items) == pytest.approx(5.0)
    assert [item.file_path for item in items] == ["a.mp4", "b.mp4"]


def test_material_pool_is_cycled_when_footage_is_shorter_than_narration(monkeypatch):
    _material_metadata(monkeypatch, [3.0])

    items = video.plan_subclips_for_narration(["a.mp4"], [3.0, 3.0])

    assert sum(item.duration for item in items) == pytest.approx(6.0)


def test_planning_does_not_spin_on_zero_length_material(monkeypatch):
    monkeypatch.setattr(
        video, "_read_material_metadata", lambda paths: [("a.mp4", 0.0, 10, 10)]
    )

    assert video.plan_subclips_for_narration(["a.mp4"], [5.0]) == []


def test_clip_speed_scales_the_source_footage_consumed(monkeypatch):
    _material_metadata(monkeypatch, [30.0])

    items = video.plan_subclips_for_narration(["a.mp4"], [4.0], clip_speed=2.0)

    # 4 playback seconds at 2x need 8 seconds of source footage.
    assert sum(item.duration for item in items) == pytest.approx(8.0)


def test_planning_is_empty_without_materials(monkeypatch):
    monkeypatch.setattr(video, "_read_material_metadata", lambda paths: [])

    assert video.plan_subclips_for_narration(["a.mp4"], [5.0]) == []


SRT = """1
00:00:00,000 --> 00:00:02,500
Primeira frase.

2
00:00:02,500 --> 00:00:07,250
Segunda frase, mais longa.
"""


def test_srt_is_parsed_into_second_ranges(tmp_path):
    path = tmp_path / "sub.srt"
    path.write_text(SRT, encoding="utf-8")

    assert subtitle.file_to_time_ranges(str(path)) == [(0.0, 2.5), (2.5, 7.25)]


def test_missing_subtitle_file_yields_no_ranges():
    assert subtitle.file_to_time_ranges("does-not-exist.srt") == []


class _Cue:
    def __init__(self, start, end):
        self.start = start
        self.end = end


class _Delta:
    def __init__(self, seconds):
        self._seconds = seconds

    def total_seconds(self):
        return self._seconds


class _SubMaker:
    def __init__(self, cues=None, offset=None):
        if cues is not None:
            self.cues = cues
        if offset is not None:
            self.offset = offset


def test_narration_segments_from_edge_cues():
    sub_maker = _SubMaker(
        cues=[_Cue(_Delta(0.0), _Delta(1.5)), _Cue(_Delta(1.5), _Delta(4.0))]
    )

    assert voice.get_narration_segments(sub_maker) == [(0.0, 1.5), (1.5, 4.0)]


def test_narration_segments_from_legacy_offsets():
    # Legacy offsets are in 100-nanosecond units.
    sub_maker = _SubMaker(offset=[(0, 15000000), (15000000, 40000000)])

    assert voice.get_narration_segments(sub_maker) == [(0.0, 1.5), (1.5, 4.0)]


def test_narration_segments_without_sub_maker():
    assert voice.get_narration_segments(None) == []


def test_resolve_prefers_the_subtitle_file(tmp_path):
    path = tmp_path / "sub.srt"
    path.write_text(SRT, encoding="utf-8")
    sub_maker = _SubMaker(cues=[_Cue(_Delta(0.0), _Delta(99.0))])

    assert task.resolve_narration_segments(str(path), sub_maker) == [
        (0.0, 2.5),
        (2.5, 7.25),
    ]


def test_resolve_falls_back_to_sub_maker_without_subtitles():
    sub_maker = _SubMaker(cues=[_Cue(_Delta(0.0), _Delta(3.0))])

    assert task.resolve_narration_segments("", sub_maker) == [(0.0, 3.0)]


def test_resolve_without_any_timing_source():
    assert task.resolve_narration_segments("", None) == []


class _FakeAudioClip:
    def __init__(self, duration):
        self.duration = duration

    def close(self):
        pass


class _FakeVideoClip:
    def __init__(self, duration, size=(1080, 1920)):
        self.duration = duration
        self.size = size
        self.w, self.h = size

    def subclipped(self, start_time, end_time):
        return _FakeVideoClip(end_time - start_time, self.size)

    def with_speed_scaled(self, factor):
        return _FakeVideoClip(self.duration / factor, self.size)

    def close(self):
        pass


def _run_combine(monkeypatch, tmp_path, *, source_duration, audio_duration, **kwargs):
    """Run combine_videos against fake clips, returning the rendered durations."""

    written = []
    monkeypatch.setattr(
        video, "AudioFileClip", lambda *_a, **_k: _FakeAudioClip(audio_duration)
    )
    monkeypatch.setattr(
        video, "_open_video_clip_quietly", lambda *_a, **_k: _FakeVideoClip(source_duration)
    )
    monkeypatch.setattr(
        video,
        "_write_videofile_with_codec_fallback",
        lambda clip, *_a, **_k: written.append(round(clip.duration, 4)),
    )
    monkeypatch.setattr(video, "concat_video_clips_with_ffmpeg", lambda **_k: None)
    monkeypatch.setattr(video, "delete_files", lambda *_a, **_k: None)

    video.combine_videos(
        combined_video_path=str(tmp_path / "combined.mp4"),
        video_paths=["a.mp4", "b.mp4"],
        audio_file="audio.mp3",
        video_concat_mode=video.VideoConcatMode.sequential,
        **kwargs,
    )
    return written


def test_combine_videos_renders_clips_on_narration_boundaries(monkeypatch, tmp_path):
    # Sentences of 2s, 2s, 3s and 1s against a 5s cap.
    segments = [(0, 2), (2, 4), (4, 7), (7, 8)]

    written = _run_combine(
        monkeypatch,
        tmp_path,
        source_duration=30.0,
        audio_duration=8.0,
        max_clip_duration=5,
        narration_segments=segments,
    )

    # Two slots of 4s each — cuts fall at 4s and 8s, both sentence boundaries,
    # instead of the fixed 5s grid that used to cut mid-sentence.
    assert written == [4.0, 4.0]


def test_combine_videos_without_segments_keeps_fixed_length_slicing(
    monkeypatch, tmp_path
):
    written = _run_combine(
        monkeypatch,
        tmp_path,
        source_duration=30.0,
        audio_duration=8.0,
        max_clip_duration=5,
    )

    # Legacy behaviour: fixed 5s chunks regardless of what is being said.
    assert written and all(duration == 5.0 for duration in written[:1])


def test_combine_videos_falls_back_when_materials_are_unusable(monkeypatch, tmp_path):
    monkeypatch.setattr(video, "_read_material_metadata", lambda paths: [])

    written = _run_combine(
        monkeypatch,
        tmp_path,
        source_duration=30.0,
        audio_duration=8.0,
        max_clip_duration=5,
        narration_segments=[(0, 2), (2, 4)],
    )

    # Planning produced nothing, so the fixed-length path still fills the video.
    assert written
