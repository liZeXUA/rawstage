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
    Script, Scene, Transition, AudioEvent, ExpressionEvent,
    Assets,
)
from rawstage.asset_loader import load_image, clear_cache
from rawstage.engine.timeline import evaluate_timeline
from rawstage.engine.compositor import composite_frame, CANVAS_W, CANVAS_H
from rawstage.encoder import encode_video, encode_video_pipe
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
    if keep_frames:
        # Legacy path: render to PNG files, then encode
        temp_dir = Path(tempfile.mkdtemp(prefix="rawstage_"))
        try:
            _render_frames(script, assets_root, temp_dir, fps, verbose, progress_cb)
            _encode_result(script, assets_root, temp_dir, output_path, fps, preset)
        finally:
            if verbose:
                print(f"  Temp frames kept at: {temp_dir}")
            clear_cache()
    else:
        # Fast path: pipe raw RGB directly to ffmpeg
        _render_pipe(script, assets_root, output_path, fps, preset, verbose, progress_cb)
        clear_cache()


def _render_pipe(
    script: Script,
    assets_root: Path,
    output_path: Path,
    fps: int,
    preset: str,
    verbose: bool,
    progress_cb: Callable[[int, int], None] | None,
) -> None:
    """Render frames and pipe them directly to ffmpeg via stdin."""
    items = script.blocks
    scenes_list = [b for b in items if isinstance(b, Scene)]

    # Pre-load all scene images
    scenes_data: list[dict] = []
    for scene in scenes_list:
        images = _load_scene_images(scene, script, assets_root)
        chars = {k: v for k, v in images.items() if k in script.assets.characters}
        exprs = {k: v for k, v in images.items() if k in script.assets.expressions}
        facs = {k: v for k, v in images.items() if k in script.assets.facilities}
        scenes_data.append({
            "scene": scene,
            "chars": chars,
            "exprs": exprs,
            "facs": facs,
        })

    total_duration, segments = _build_timeline(items)
    total_frames = math.ceil(total_duration * fps)

    if verbose:
        title = script.meta.get("title", "untitled")
        print(f"Rendering \"{title}\": {total_frames} frames at {fps} fps "
              f"({total_duration:.1f}s)")

    audio_inputs = _compute_audio_inputs(script, assets_root, items, segments)

    def frame_generator():
        for frame_num in range(total_frames):
            t = frame_num / fps
            frame_img = _render_single_frame(t, segments, scenes_data, script, fps)
            yield frame_img
            if progress_cb:
                progress_cb(frame_num, total_frames)
            elif verbose and frame_num % 24 == 0:
                print(f"  Frame {frame_num}/{total_frames} (t={t:.2f}s)")

    encode_video_pipe(
        output_path=output_path,
        fps=fps,
        total_frames=total_frames,
        canvas_w=CANVAS_W,
        canvas_h=CANVAS_H,
        preset=preset,
        audio_inputs=audio_inputs if audio_inputs else None,
        frame_iter=frame_generator(),
    )


def _render_frames(
    script: Script,
    assets_root: Path,
    temp_dir: Path,
    fps: int,
    verbose: bool,
    progress_cb: Callable[[int, int], None] | None,
) -> None:
    items = script.blocks

    scenes_list = [b for b in items if isinstance(b, Scene)]
    scenes_data: list[dict] = []
    for scene in scenes_list:
        images = _load_scene_images(scene, script, assets_root)
        chars = {k: v for k, v in images.items() if k in script.assets.characters}
        exprs = {k: v for k, v in images.items() if k in script.assets.expressions}
        facs = {k: v for k, v in images.items() if k in script.assets.facilities}
        scenes_data.append({
            "scene": scene,
            "chars": chars,
            "exprs": exprs,
            "facs": facs,
        })

    total_duration, segments = _build_timeline(items)
    total_frames = math.ceil(total_duration * fps)

    if verbose:
        title = script.meta.get("title", "untitled")
        print(f"Rendering \"{title}\": {total_frames} frames at {fps} fps "
              f"({total_duration:.1f}s)")

    for frame_num in range(total_frames):
        t = frame_num / fps

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
    seg = None
    for s in segments:
        if s["global_start"] <= t < s["global_end"]:
            seg = s
            break
    if seg is None:
        seg = segments[-1]
        t = seg["global_end"]

    if seg["type"] == "scene":
        sd = scenes_data[seg["scene_index"]]
        scene = sd["scene"]
        scene_t = t - seg["scene_start"]
        state = evaluate_timeline(scene, script.assets, min(scene_t, scene.duration))
        return composite_frame(sd["chars"], sd["exprs"], sd["facs"], state)

    elif seg["type"] == "transition":
        transition = seg["transition"]
        dt = transition.duration
        progress = (t - seg["global_start"]) / max(dt, 0.001)

        # Scene A (outgoing)
        sd_a = scenes_data[seg["scene_a_index"]]
        scene_a = sd_a["scene"]
        scene_a_t = t - seg["scene_a_start"]
        state_a = evaluate_timeline(scene_a, script.assets, min(scene_a_t, scene_a.duration))
        frame_a = composite_frame(sd_a["chars"], sd_a["exprs"], sd_a["facs"], state_a)

        # Scene B (incoming)
        sd_b = scenes_data[seg["scene_b_index"]]
        scene_b = sd_b["scene"]
        scene_b_t = t - seg["scene_b_start"]
        state_b = evaluate_timeline(scene_b, script.assets, min(scene_b_t, scene_b.duration))
        frame_b = composite_frame(sd_b["chars"], sd_b["exprs"], sd_b["facs"], state_b)

        return _blend_frames(frame_a, frame_b, progress, transition.type)

    return Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 255))


def _blend_frames(
    frame_a: Image.Image,
    frame_b: Image.Image,
    progress: float,
    blend_type: str,
) -> Image.Image:
    if blend_type in ("fade", "dissolve"):
        return Image.blend(
            frame_a.convert("RGBA"), frame_b.convert("RGBA"), progress)

    elif blend_type == "wipe_left":
        result = frame_a.copy()
        split = int(CANVAS_W * progress)
        if split > 0:
            crop_b = frame_b.crop((0, 0, split, CANVAS_H))
            result.paste(crop_b, (0, 0))
        return result

    elif blend_type == "wipe_right":
        result = frame_a.copy()
        split = int(CANVAS_W * (1.0 - progress))
        if split < CANVAS_W:
            crop_b = frame_b.crop((split, 0, CANVAS_W, CANVAS_H))
            result.paste(crop_b, (split, 0))
        return result

    return Image.blend(
        frame_a.convert("RGBA"), frame_b.convert("RGBA"), progress)


def _build_timeline(items: list) -> tuple[float, list[dict]]:
    scenes: list[Scene] = []
    transitions: list[tuple[int, Transition]] = []
    for i, item in enumerate(items):
        if isinstance(item, Scene):
            scenes.append(item)
        elif isinstance(item, Transition):
            transitions.append((len(scenes) - 1, item))

    if not scenes:
        return 0.0, []

    segments: list[dict] = []
    current_global = 0.0
    prev_overlap = 0.0

    for i, scene in enumerate(scenes):
        trans = None
        for si, t in transitions:
            if si == i:
                trans = t
                break

        scene_t0 = current_global - prev_overlap

        if trans:
            overlap = trans.duration
            scene_end = scene_t0 + scene.duration

            if scene.duration > overlap:
                segments.append({
                    "type": "scene",
                    "global_start": current_global,
                    "global_end": scene_end - overlap,
                    "scene_index": i,
                    "scene_start": scene_t0,
                })

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
    scenes_list = [it for it in items if isinstance(it, Scene)]

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
    """Load all images referenced by a scene: facilities, characters, expressions."""
    images = {}

    # Facilities
    for place in scene.initial_facilities:
        fac_asset = script.assets.facilities[place.facility]
        images[place.facility] = load_image(assets_root / fac_asset.src)

    # Facilities referenced by holes (may not be in initial_facilities)
    for hole in scene.holes:
        if hole.sample_facility not in images:
            fac_asset = script.assets.facilities.get(hole.sample_facility)
            if fac_asset:
                images[hole.sample_facility] = load_image(assets_root / fac_asset.src)

    # Characters in initial_characters
    for place in scene.initial_characters:
        char_asset = script.assets.characters[place.character]
        images[place.character] = load_image(assets_root / char_asset.src)

    # Characters and expressions referenced in events
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
