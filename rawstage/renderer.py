"""Full-script rendering orchestration.

Walks Script.blocks (Scene + Transition interleaved), renders every frame
to a temp directory, then encodes via ffmpeg.
"""

import math
import shutil
import tempfile
from pathlib import Path
from collections.abc import Callable

from PIL import Image

from rawstage.parser.models import (
    Script, Scene, Transition, AudioEvent,
    Assets,
)
from rawstage.asset_loader import load_image, clear_cache
from rawstage.engine.timeline import evaluate_timeline
from rawstage.engine.compositor import composite_frame, CANVAS_W, CANVAS_H
from rawstage.encoder import encode_video
from rawstage.errors import RawStageError


def render_script(
    script: Script,
    assets_root: Path,
    output_path: Path,
    fps: int = 24,
    preset: str = "ultrafast",
    keep_frames: bool = False,
    verbose: bool = False,
    progress_cb: Callable[[int, int], None] | None = None,
) -> None:
    """Render a complete script to MP4 video.

    Args:
        script: Parsed Script with interleaved Scene and Transition blocks.
        assets_root: Root directory for asset file paths.
        output_path: Output MP4 file path.
        fps: Frames per second.
        preset: x264 preset (ultrafast for dev, medium for production).
        keep_frames: If True, keep temp PNG directory after encoding.
        verbose: Print progress information.
        progress_cb: Optional callback(current_frame, total_frames) for progress.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="rawstage_"))
    try:
        _render_frames(script, assets_root, temp_dir, fps, verbose, progress_cb)
        _encode_result(script, assets_root, temp_dir, output_path, fps, preset)
    finally:
        if not keep_frames:
            shutil.rmtree(temp_dir, ignore_errors=True)
        elif verbose:
            print(f"  Temp frames kept at: {temp_dir}")
        clear_cache()


def _render_frames(
    script: Script,
    assets_root: Path,
    temp_dir: Path,
    fps: int,
    verbose: bool,
    progress_cb: Callable[[int, int], None] | None,
) -> None:
    """Render all frames to temp_dir/frame_000000.png ..."""
    # Extract scenes and transitions in order
    items = script.blocks  # list[Scene | Transition]

    # Pre-load images per scene (indexed by scene order, matching _build_timeline)
    scenes_list = [b for b in items if isinstance(b, Scene)]
    scenes_data: list[dict] = []
    for scene in scenes_list:
        images = _load_scene_images(scene, script, assets_root)
        bg = images.pop("__bg__")
        chars = {k: v for k, v in images.items() if k in script.assets.characters}
        exprs = {k: v for k, v in images.items() if k in script.assets.expressions}
        scenes_data.append({
            "scene": scene,
            "bg": bg,
            "chars": chars,
            "exprs": exprs,
        })

    # Build global timeline
    total_duration, segments = _build_timeline(items)
    total_frames = math.ceil(total_duration * fps)

    if verbose:
        title = script.meta.get("title", "untitled")
        print(f"Rendering \"{title}\": {total_frames} frames at {fps} fps "
              f"({total_duration:.1f}s)")

    scene_index = 0
    for frame_num in range(total_frames):
        t = frame_num / fps

        # Find which segment this frame belongs to
        frame_img = _render_single_frame(t, segments, scenes_data, script, fps)

        path = temp_dir / f"frame_{frame_num:06d}.png"
        frame_img.save(path)

        if progress_cb:
            progress_cb(frame_num, total_frames)
        elif verbose and frame_num % 24 == 0:
            print(f"  Frame {frame_num}/{total_frames} (t={t:.2f}s)")

    if verbose:
        print(f"  Rendered {total_frames} frames to {temp_dir}/")


def _render_single_frame(
    t: float,
    segments: list[dict],
    scenes_data: list[dict],
    script: Script,
    fps: int,
) -> Image.Image:
    """Render one frame at global time t, handling transitions."""
    # Find the segment containing time t
    seg = None
    for s in segments:
        if s["global_start"] <= t < s["global_end"]:
            seg = s
            break
    if seg is None:
        # Past the end, render last scene at its final time
        seg = segments[-1]
        t = seg["global_end"]

    if seg["type"] == "scene":
        sd = scenes_data[seg["scene_index"]]
        scene = sd["scene"]
        scene_t = t - seg["scene_start"]
        state = evaluate_timeline(scene, script.assets, min(scene_t, scene.duration))
        return composite_frame(sd["bg"], sd["chars"], sd["exprs"], state)

    elif seg["type"] == "transition":
        # Blend two scenes
        transition = seg["transition"]
        dt = transition.duration
        progress = (t - seg["global_start"]) / max(dt, 0.001)

        # Scene A (outgoing)
        sd_a = scenes_data[seg["scene_a_index"]]
        scene_a = sd_a["scene"]
        scene_a_t = t - seg["scene_a_start"]
        state_a = evaluate_timeline(scene_a, script.assets, min(scene_a_t, scene_a.duration))
        frame_a = composite_frame(sd_a["bg"], sd_a["chars"], sd_a["exprs"], state_a)

        # Scene B (incoming)
        sd_b = scenes_data[seg["scene_b_index"]]
        scene_b = sd_b["scene"]
        scene_b_t = t - seg["scene_b_start"]
        state_b = evaluate_timeline(scene_b, script.assets, min(scene_b_t, scene_b.duration))
        frame_b = composite_frame(sd_b["bg"], sd_b["chars"], sd_b["exprs"], state_b)

        return _blend_frames(frame_a, frame_b, progress, transition.type)

    # Fallback: black frame
    return Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 255))


def _blend_frames(
    frame_a: Image.Image,
    frame_b: Image.Image,
    progress: float,
    blend_type: str,
) -> Image.Image:
    """Blend two frames during a transition.

    progress: 0.0 = fully scene A, 1.0 = fully scene B.
    """
    if blend_type in ("fade", "dissolve"):
        # Crossfade: uniform alpha blend
        alpha_b = progress
        return Image.blend(
            frame_a.convert("RGBA"), frame_b.convert("RGBA"), alpha_b)

    elif blend_type == "wipe_left":
        # Scene B reveals from left to right
        result = frame_a.copy()
        split = int(CANVAS_W * progress)
        if split > 0:
            crop_b = frame_b.crop((0, 0, split, CANVAS_H))
            result.paste(crop_b, (0, 0))
        return result

    elif blend_type == "wipe_right":
        # Scene B reveals from right to left
        result = frame_a.copy()
        split = int(CANVAS_W * (1.0 - progress))
        if split < CANVAS_W:
            crop_b = frame_b.crop((split, 0, CANVAS_W, CANVAS_H))
            result.paste(crop_b, (split, 0))
        return result

    # Unknown: crossfade
    return Image.blend(
        frame_a.convert("RGBA"), frame_b.convert("RGBA"), progress)


def _build_timeline(items: list) -> tuple[float, list[dict]]:
    """Compute global time ranges for each segment.

    Returns (total_duration, list of segment dicts). Each segment dict has:
      type: "scene" or "transition"
      global_start, global_end
      For scenes: scene_index, scene_start
      For transitions: scene_a_index, scene_b_index, scene_a_start, scene_b_start,
                       transition
    """
    # First pass: compute scene durations and identify transitions
    scenes: list[Scene] = []
    transitions: list[tuple[int, Transition]] = []  # (position_between_scenes, transition)
    for i, item in enumerate(items):
        if isinstance(item, Scene):
            scenes.append(item)
        elif isinstance(item, Transition):
            transitions.append((len(scenes) - 1, item))

    if not scenes:
        return 0.0, []

    # Build timeline accounting for transition overlaps.
    # current_global tracks the next unallocated global time.
    # prev_overlap tracks how much of the current scene was already covered
    # by a transition from the previous scene.
    segments: list[dict] = []
    current_global = 0.0
    prev_overlap = 0.0

    for i, scene in enumerate(scenes):
        # Find transition after this scene (if any)
        trans = None
        for si, t in transitions:
            if si == i:
                trans = t
                break

        # Scene t=0 in global time (accounting for overlap from previous transition)
        scene_t0 = current_global - prev_overlap

        if trans:
            overlap = trans.duration
            scene_end = scene_t0 + scene.duration

            # Scene non-overlap portion (before transition starts)
            if scene.duration > overlap:
                segments.append({
                    "type": "scene",
                    "global_start": current_global,
                    "global_end": scene_end - overlap,
                    "scene_index": i,
                    "scene_start": scene_t0,
                })

            # Transition overlap portion
            segments.append({
                "type": "transition",
                "global_start": scene_end - overlap,
                "global_end": scene_end,
                "scene_a_index": i,
                "scene_b_index": i + 1,
                "scene_a_start": scene_t0,
                "scene_b_start": scene_end - overlap,
                "transition": trans,
            })

            current_global = scene_end
            prev_overlap = overlap
        else:
            # No transition after this scene. Scene runs from current_global
            # for its remaining (un-overlapped) duration.
            remaining = scene.duration - prev_overlap
            segment_end = current_global + remaining
            segments.append({
                "type": "scene",
                "global_start": current_global,
                "global_end": segment_end,
                "scene_index": i,
                "scene_start": scene_t0,
            })
            current_global = segment_end
            prev_overlap = 0.0

    total_duration = segments[-1]["global_end"] if segments else 0.0
    return total_duration, segments


def _encode_result(
    script: Script,
    assets_root: Path,
    temp_dir: Path,
    output_path: Path,
    fps: int,
    preset: str,
) -> None:
    """Collect audio and call encoder."""
    items = script.blocks
    segments = _build_timeline(items)[1]
    total_frames = math.ceil(
        (segments[-1]["global_end"] if segments else 0.0) * fps)

    if not segments:
        return

    audio_inputs = _compute_audio_inputs(script, assets_root, items, segments)

    encode_video(
        frame_dir=temp_dir,
        output_path=output_path,
        fps=fps,
        total_frames=total_frames,
        preset=preset,
        audio_inputs=audio_inputs if audio_inputs else None,
    )


def _compute_audio_inputs(
    script: Script,
    assets_root: Path,
    items: list[Scene | Transition],
    segments: list[dict],
) -> list[tuple[Path, float, float, bool, float]]:
    """Map scene audio events to global time for the encoder."""
    scenes_list = [it for it in items if isinstance(it, Scene)]

    # Compute the earliest global t=0 for each scene
    scene_t0: dict[str, float] = {}
    for seg in segments:
        if seg["type"] == "scene":
            scene = scenes_list[seg["scene_index"]]
            t0 = seg["scene_start"]
        elif seg["type"] == "transition":
            scene = scenes_list[seg["scene_b_index"]]
            t0 = seg["scene_b_start"]
        else:
            continue
        if scene.id not in scene_t0 or t0 < scene_t0[scene.id]:
            scene_t0[scene.id] = t0

    result: list[tuple[Path, float, float, bool, float]] = []
    for scene in scenes_list:
        t0 = scene_t0.get(scene.id)
        if t0 is None:
            continue

        for event in scene.events:
            if not isinstance(event, AudioEvent):
                continue
            if event.action not in ("play", "play_once"):
                continue

            audio_asset = script.assets.audios.get(event.ref)
            if audio_asset is None:
                continue

            audio_path = assets_root / audio_asset.src
            if not audio_path.exists():
                continue

            global_start = t0 + event.start
            duration = event.duration if event.duration > 0 else 0.0
            result.append((audio_path, global_start, duration, event.loop, event.volume))

    return result


def _load_scene_images(scene: Scene, script: Script, assets_root: Path) -> dict:
    """Load all images referenced by a scene."""
    images = {}

    bg_asset = script.assets.backgrounds[scene.background]
    images["__bg__"] = load_image(assets_root / bg_asset.src)

    for place in scene.initial_characters:
        char_asset = script.assets.characters[place.character]
        images[place.character] = load_image(assets_root / char_asset.src)

    from rawstage.parser.models import ExpressionEvent
    for event in scene.events:
        char_id = getattr(event, "character", None)
        if char_id and char_id not in images:
            char_asset = script.assets.characters.get(char_id)
            if char_asset:
                images[char_id] = load_image(assets_root / char_asset.src)

        if isinstance(event, ExpressionEvent):
            expr_asset = script.assets.expressions.get(event.set)
            if expr_asset and event.set not in images:
                images[event.set] = load_image(assets_root / expr_asset.src)

    return images
