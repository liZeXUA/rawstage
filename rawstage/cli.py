import argparse
import math
import sys
from pathlib import Path

from tqdm import tqdm

from rawstage.parser import parse_script
from rawstage.parser.models import ExpressionEvent
from rawstage.asset_loader import load_image, clear_cache
from rawstage.engine.compositor import composite_frame, CANVAS_W, CANVAS_H
from rawstage.engine.timeline import evaluate_timeline
from rawstage.renderer import render_script
from rawstage.errors import RawStageError


def main():
    parser = argparse.ArgumentParser(
        prog="rawstage",
        description="Render ComicDirector ML scripts to video"
    )
    subparsers = parser.add_subparsers(dest="command")

    # render
    render_parser = subparsers.add_parser("render", help="Render a script to video")
    render_parser.add_argument("script", type=Path, help="Path to ComicDirector ML XML")
    render_parser.add_argument("--assets", type=Path, required=True,
                               help="Root directory for assets")
    render_parser.add_argument("--output", type=Path, default=Path("output.mp4"),
                               help="Output MP4 path")
    render_parser.add_argument("--fps", type=int, default=24,
                               help="Frames per second (default: 24)")
    render_parser.add_argument("--keep-frames", action="store_true",
                               help="Keep temporary frame PNGs after encoding")
    render_parser.add_argument("--progress", action="store_true",
                               help="Show progress bar during rendering")
    render_parser.add_argument("--verbose", "-v", action="store_true",
                               help="Verbose logging")

    # frame command: render a single static frame
    frame_parser = subparsers.add_parser("frame", help="Render a scene frame")
    frame_parser.add_argument("script", type=Path, help="Path to ComicDirector ML XML")
    frame_parser.add_argument("--assets", type=Path, required=True,
                              help="Root directory for assets")
    frame_parser.add_argument("--scene", type=int, default=1,
                              help="Scene number to render (1-based, default: 1)")
    frame_parser.add_argument("--time", type=float, default=0.0,
                              help="Time in seconds within the scene (default: 0)")
    frame_parser.add_argument("--output", type=Path, default=Path("frame.png"),
                              help="Output PNG path")
    frame_parser.add_argument("--verbose", "-v", action="store_true",
                              help="Verbose logging")

    # animate command: render full PNG sequence for a scene
    animate_parser = subparsers.add_parser(
        "animate", help="Render a scene as a PNG frame sequence")
    animate_parser.add_argument("script", type=Path, help="Path to ComicDirector ML XML")
    animate_parser.add_argument("--assets", type=Path, required=True,
                                help="Root directory for assets")
    animate_parser.add_argument("--scene", type=int, default=1,
                                help="Scene number (1-based, default: 1)")
    animate_parser.add_argument("--fps", type=int, default=24,
                                help="Frames per second (default: 24)")
    animate_parser.add_argument("--output", type=Path, default=Path("frames"),
                                help="Output directory for PNG frames")
    animate_parser.add_argument("--every", type=int, default=1,
                                help="Render every Nth frame (default: 1 = all)")
    animate_parser.add_argument("--progress", action="store_true",
                                help="Show progress bar during rendering")
    animate_parser.add_argument("--verbose", "-v", action="store_true",
                                help="Verbose logging")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "frame":
            _cmd_frame(args)
        elif args.command == "render":
            _cmd_render(args)
        elif args.command == "animate":
            _cmd_animate(args)
    except RawStageError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _load_scene_images(scene, script, assets_root):
    """Load all images referenced by a scene: characters, expressions, facilities."""
    images = {}

    # Facilities
    for place in scene.initial_facilities:
        fac_asset = script.assets.facilities[place.facility]
        images[place.facility] = load_image(assets_root / fac_asset.src)

    # Characters referenced in initial_characters
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


def _split_images(images, script):
    """Split loaded images into char, expr, fac dicts."""
    char_images = {}
    expr_images = {}
    fac_images = {}
    for k, v in images.items():
        if k in script.assets.characters:
            char_images[k] = v
        elif k in script.assets.expressions:
            expr_images[k] = v
        elif k in script.assets.facilities:
            fac_images[k] = v
    return char_images, expr_images, fac_images


def _cmd_frame(args) -> None:
    script = parse_script(args.script)
    scene = _get_scene(script, args.scene)

    if args.verbose:
        _print_scene_info(scene, script)

    images = _load_scene_images(scene, script, args.assets)
    char_images, expr_images, fac_images = _split_images(images, script)

    state = evaluate_timeline(scene, script.assets, args.time)

    frame = composite_frame(char_images, expr_images, fac_images, state)
    frame.save(args.output)
    print(f"Saved: {args.output} ({frame.width}x{frame.height})")

    clear_cache()


def _cmd_animate(args) -> None:
    script = parse_script(args.script)
    scene = _get_scene(script, args.scene)

    if args.verbose:
        _print_scene_info(scene, script)
        print(f"  FPS: {args.fps}")

    images = _load_scene_images(scene, script, args.assets)
    char_images, expr_images, fac_images = _split_images(images, script)

    total_frames = math.ceil(scene.duration * args.fps)
    args.output.mkdir(parents=True, exist_ok=True)

    pbar = None
    if args.progress:
        pbar = tqdm(total=total_frames, unit="fr", desc="Animating",
                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]")

    rendered = 0
    for frame_num in range(total_frames):
        if frame_num % args.every != 0:
            continue

        t = frame_num / args.fps
        state = evaluate_timeline(scene, script.assets, t)
        frame = composite_frame(char_images, expr_images, fac_images, state)
        path = args.output / f"frame_{frame_num:06d}.png"
        frame.save(path)
        rendered += 1

        if pbar:
            pbar.n = frame_num + 1
            pbar.refresh()

        if args.verbose and not args.progress and frame_num % 24 == 0:
            print(f"  Frame {frame_num}/{total_frames} (t={t:.2f}s)")

    if pbar:
        pbar.close()

    print(f"Rendered {rendered} frames to {args.output}/")
    clear_cache()


def _cmd_render(args) -> None:
    script = parse_script(args.script)

    if args.verbose:
        title = script.meta.get("title", "untitled")
        scenes = [b for b in script.blocks if hasattr(b, "initial_camera")]
        transitions = [b for b in script.blocks if hasattr(b, "type")]
        print(f"Script: \"{title}\"")
        print(f"  Scenes: {len(scenes)}")
        print(f"  Transitions: {len(transitions)}")
        print(f"  FPS: {args.fps}")

    progress_cb = None
    if args.progress:
        pbar = tqdm(total=0, unit="fr", desc="Rendering",
                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]")
        def progress_cb(current, total):
            pbar.total = total
            pbar.n = current + 1
            pbar.refresh()

    try:
        render_script(
            script=script,
            assets_root=args.assets,
            output_path=args.output,
            fps=args.fps,
            keep_frames=args.keep_frames,
            verbose=args.verbose,
            progress_cb=progress_cb,
        )
    finally:
        if args.progress:
            pbar.close()

    print(f"Encoded: {args.output}")


def _get_scene(script, scene_num: int):
    scenes = [b for b in script.blocks if hasattr(b, "initial_camera")]
    idx = scene_num - 1
    if idx < 0 or idx >= len(scenes):
        print(f"Error: scene {scene_num} not found (script has {len(scenes)} scenes)",
              file=sys.stderr)
        sys.exit(1)
    return scenes[idx]


def _print_scene_info(scene, script) -> None:
    print(f"Scene {scene.id}: \"{script.meta.get('title', 'untitled')}\"")
    print(f"  Duration: {scene.duration}s")
    chars = [p.character for p in scene.initial_characters]
    facs = [p.facility for p in scene.initial_facilities]
    print(f"  Characters: {chars}")
    print(f"  Facilities: {facs}")
    print(f"  Events: {len(scene.events)}")
