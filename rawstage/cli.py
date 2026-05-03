import argparse
import math
import sys
from pathlib import Path

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
    """Load all images referenced by a scene: background, characters, expressions."""
    images = {}

    # Background
    bg_asset = script.assets.backgrounds[scene.background]
    images["__bg__"] = load_image(assets_root / bg_asset.src)

    # Characters referenced in initial_characters
    for place in scene.initial_characters:
        char_asset = script.assets.characters[place.character]
        images[place.character] = load_image(assets_root / char_asset.src)

    # Characters and expressions referenced in events
    for event in scene.events:
        char_id = getattr(event, "character", None)
        if char_id and char_id not in images:
            char_asset = script.assets.characters[char_id]
            images[char_id] = load_image(assets_root / char_asset.src)

        if isinstance(event, ExpressionEvent):
            expr_asset = script.assets.expressions.get(event.set)
            if expr_asset:
                images[event.set] = load_image(assets_root / expr_asset.src)

    return images


def _cmd_frame(args) -> None:
    script = parse_script(args.script)
    scene = _get_scene(script, args.scene)

    if args.verbose:
        _print_scene_info(scene, script)

    images = _load_scene_images(scene, script, args.assets)
    bg_image = images.pop("__bg__")
    char_images = {k: v for k, v in images.items() if k in script.assets.characters}
    expr_images = {k: v for k, v in images.items() if k in script.assets.expressions}

    # Use timeline evaluator for the requested time
    state = evaluate_timeline(scene, script.assets, args.time)

    frame = composite_frame(bg_image, char_images, expr_images, state)
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
    bg_image = images.pop("__bg__")
    # Split into character and expression images
    char_images = {}
    expr_images = {}
    for k, v in images.items():
        if k in script.assets.characters:
            char_images[k] = v
        elif k in script.assets.expressions:
            expr_images[k] = v

    total_frames = math.ceil(scene.duration * args.fps)
    args.output.mkdir(parents=True, exist_ok=True)

    rendered = 0
    for frame_num in range(total_frames):
        if frame_num % args.every != 0:
            continue

        t = frame_num / args.fps
        state = evaluate_timeline(scene, script.assets, t)
        frame = composite_frame(bg_image, char_images, expr_images, state)
        path = args.output / f"frame_{frame_num:06d}.png"
        frame.save(path)
        rendered += 1

        if args.verbose and frame_num % 24 == 0:
            print(f"  Frame {frame_num}/{total_frames} (t={t:.2f}s)")

    print(f"Rendered {rendered} frames to {args.output}/")
    clear_cache()


def _cmd_render(args) -> None:
    script = parse_script(args.script)

    if args.verbose:
        title = script.meta.get("title", "untitled")
        scenes = [b for b in script.blocks if hasattr(b, "background")]
        transitions = [b for b in script.blocks if hasattr(b, "type")]
        print(f"Script: \"{title}\"")
        print(f"  Scenes: {len(scenes)}")
        print(f"  Transitions: {len(transitions)}")
        print(f"  FPS: {args.fps}")

    render_script(
        script=script,
        assets_root=args.assets,
        output_path=args.output,
        fps=args.fps,
        keep_frames=args.keep_frames,
        verbose=args.verbose,
    )

    print(f"Encoded: {args.output}")


def _get_scene(script, scene_num: int):
    scenes = [b for b in script.blocks if hasattr(b, "background")]
    idx = scene_num - 1
    if idx < 0 or idx >= len(scenes):
        print(f"Error: scene {scene_num} not found (script has {len(scenes)} scenes)",
              file=sys.stderr)
        sys.exit(1)
    return scenes[idx]


def _print_scene_info(scene, script) -> None:
    print(f"Scene {scene.id}: \"{script.meta.get('title', 'untitled')}\"")
    print(f"  Background: {scene.background}")
    print(f"  Duration: {scene.duration}s")
    print(f"  Characters: {[p.character for p in scene.initial_characters]}")
    print(f"  Events: {len(scene.events)}")
