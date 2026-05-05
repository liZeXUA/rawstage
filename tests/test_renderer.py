import math
import shutil
from pathlib import Path

import pytest
from PIL import Image

from rawstage.parser import parse_script
from rawstage.renderer import (
    _build_timeline,
    _blend_frames,
    render_script,
)
from rawstage.engine.compositor import CANVAS_W, CANVAS_H

FIXTURES = Path(__file__).parent / "fixtures"


def _make_test_frames():
    """Create two solid-color test frames for blend testing."""
    a = Image.new("RGBA", (CANVAS_W, CANVAS_H), (255, 0, 0, 255))  # red
    b = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 255, 255))  # blue
    return a, b


class TestBuildTimeline:
    def test_single_scene(self):
        script = parse_script(FIXTURES / "sample.xml")
        items = script.blocks
        total_duration, segments = _build_timeline(items)

        assert total_duration == 10.0
        assert len(segments) == 1
        assert segments[0]["type"] == "scene"
        assert segments[0]["global_start"] == 0.0
        assert segments[0]["global_end"] == 10.0
        assert segments[0]["scene_index"] == 0

    def test_two_scenes_with_transition(self):
        script = parse_script(FIXTURES / "two_scene.xml")
        items = script.blocks
        total_duration, segments = _build_timeline(items)

        # Scene 1 (3s) + Scene 2 (3s) - overlap (1s) = 5s
        assert total_duration == 5.0

        assert len(segments) == 3

        # Scene 1: 0.0 to 2.0 (3.0 - 1.0 overlap)
        assert segments[0]["type"] == "scene"
        assert segments[0]["global_start"] == 0.0
        assert segments[0]["global_end"] == 2.0
        assert segments[0]["scene_index"] == 0

        # Transition: 2.0 to 3.0
        assert segments[1]["type"] == "transition"
        assert segments[1]["global_start"] == 2.0
        assert segments[1]["global_end"] == 3.0
        assert segments[1]["scene_a_index"] == 0
        assert segments[1]["scene_b_index"] == 1

        # Scene 2: 3.0 to 5.0
        assert segments[2]["type"] == "scene"
        assert segments[2]["global_start"] == 3.0
        assert segments[2]["global_end"] == 5.0
        assert segments[2]["scene_index"] == 1

    def test_scene_time_computation(self):
        script = parse_script(FIXTURES / "two_scene.xml")
        items = script.blocks
        _, segments = _build_timeline(items)

        scene2_seg = segments[2]
        assert scene2_seg["scene_start"] == 2.0

    def test_minimal_single_scene(self):
        script = parse_script(FIXTURES / "minimal.xml")
        items = script.blocks
        total_duration, segments = _build_timeline(items)

        assert total_duration == 5.0
        assert len(segments) == 1
        assert segments[0]["type"] == "scene"

    def test_no_scenes(self):
        from rawstage.parser.models import Script, Assets
        items = []
        total_duration, segments = _build_timeline(items)
        assert total_duration == 0.0
        assert segments == []


class TestBlendFrames:
    def test_fade_midpoint(self):
        a, b = _make_test_frames()
        result = _blend_frames(a, b, 0.5, "fade")
        pixel = result.getpixel((CANVAS_W // 2, CANVAS_H // 2))
        assert abs(pixel[0] - 127) < 5
        assert abs(pixel[2] - 127) < 5

    def test_fade_start(self):
        a, b = _make_test_frames()
        result = _blend_frames(a, b, 0.0, "fade")
        pixel = result.getpixel((100, 100))
        assert pixel[0] > 250  # mostly red
        assert pixel[2] < 5    # no blue

    def test_fade_end(self):
        a, b = _make_test_frames()
        result = _blend_frames(a, b, 1.0, "fade")
        pixel = result.getpixel((100, 100))
        assert pixel[2] > 250  # mostly blue
        assert pixel[0] < 5    # no red

    def test_dissolve_is_crossfade(self):
        a, b = _make_test_frames()
        result = _blend_frames(a, b, 0.5, "dissolve")
        pixel = result.getpixel((CANVAS_W // 2, CANVAS_H // 2))
        assert abs(pixel[0] - 127) < 5
        assert abs(pixel[2] - 127) < 5

    def test_wipe_left(self):
        a, b = _make_test_frames()
        result = _blend_frames(a, b, 0.5, "wipe_left")
        left = result.getpixel((CANVAS_W // 4, CANVAS_H // 2))
        right = result.getpixel((3 * CANVAS_W // 4, CANVAS_H // 2))
        assert left[2] > 250   # blue
        assert right[0] > 250  # red

    def test_wipe_right(self):
        a, b = _make_test_frames()
        result = _blend_frames(a, b, 0.5, "wipe_right")
        left = result.getpixel((CANVAS_W // 4, CANVAS_H // 2))
        right = result.getpixel((3 * CANVAS_W // 4, CANVAS_H // 2))
        assert left[0] > 250   # red
        assert right[2] > 250  # blue

    def test_unknown_type_falls_back_to_fade(self):
        a, b = _make_test_frames()
        result = _blend_frames(a, b, 0.5, "unknown_blend")
        pixel = result.getpixel((CANVAS_W // 2, CANVAS_H // 2))
        assert abs(pixel[0] - 127) < 5


class TestRenderScript:
    """End-to-end render tests. Require ffmpeg + real assets (set RAWSTAGE_ASSETS env var)."""

    @pytest.fixture(autouse=True)
    def _check_prerequisites(self):
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not available")
        import os
        assets = os.environ.get("RAWSTAGE_ASSETS", "/tmp/test_assets")
        if not Path(assets).is_dir():
            pytest.skip(f"asset dir not found: {assets}. Set RAWSTAGE_ASSETS env var.")

    def test_render_single_scene(self, tmp_path):
        script = parse_script(FIXTURES / "sample.xml")
        output = tmp_path / "output.mp4"

        render_script(
            script=script,
            assets_root=Path("/tmp/test_assets"),
            output_path=output,
            fps=12,
            preset="ultrafast",
        )

        assert output.exists()
        assert output.stat().st_size > 0

    def test_render_two_scenes_with_transition(self, tmp_path):
        script = parse_script(FIXTURES / "two_scene.xml")
        output = tmp_path / "output.mp4"

        render_script(
            script=script,
            assets_root=Path("/tmp/test_assets"),
            output_path=output,
            fps=12,
            preset="ultrafast",
        )

        assert output.exists()
        assert output.stat().st_size > 0

    def test_render_single_scene_framecount(self, tmp_path):
        script = parse_script(FIXTURES / "sample.xml")
        output = tmp_path / "output.mp4"
        fps = 12

        render_script(
            script=script,
            assets_root=Path("/tmp/test_assets"),
            output_path=output,
            fps=fps,
            preset="ultrafast",
        )

        expected_frames = math.ceil(10.0 * fps)
        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=nb_frames", "-of",
             "default=noprint_wrappers=1:nokey=1", str(output)],
            capture_output=True, text=True)
        assert int(result.stdout.strip()) == expected_frames

    def test_keep_frames(self, tmp_path):
        script = parse_script(FIXTURES / "sample.xml")
        output = tmp_path / "output.mp4"

        render_script(
            script=script,
            assets_root=Path("/tmp/test_assets"),
            output_path=output,
            fps=4,
            preset="ultrafast",
            keep_frames=True,
        )

        assert output.exists()
