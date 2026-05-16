# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RawStage — ComicDirector ML v1.0 rendering engine. Parses XML performance instructions and outputs MP4 video by compositing PNG character sprites and facilities in a layered depth system. Part of a larger AI-driven "raw-style" dynamic comic generation pipeline (LLM → XML → Video).

## Dev Setup & Commands

```bash
pip install -e .        # editable install (requires Python ≥3.11)
pytest tests/ -v        # run all tests
pytest tests/ -v -k test_parse    # run a subset by keyword
```

Requires `ffmpeg` on PATH for video encoding. Dependencies: `Pillow>=10.0`, `lxml>=5.0`, `tqdm>=4.0`. No numpy.

## CLI

```bash
# Render a complete script to MP4 (default: pipe encoding, no temp files)
rawstage render script.xml --assets ./assets/ --output out.mp4 --fps 24
rawstage render script.xml --assets ./assets/ --output out.mp4 --fps 24 --progress
rawstage render script.xml --assets ./assets/ --output out.mp4 --keep-frames  # legacy file-based

# Render a single frame at time t within a scene
rawstage frame scene.xml --assets ./assets/ --scene 1 --time 3.0 --output frame.png

# Render a full PNG frame sequence for a scene
rawstage animate scene.xml --assets ./assets/ --scene 1 --fps 24 --output frames/
rawstage animate scene.xml --assets ./assets/ --every 2 --output frames/  # every Nth frame
```

## Architecture

### Data Flow

```
XML file  →  parser/xml_parser.py  →  parser/models.py (dataclasses)
                                              │
              ┌───────────────────────────────┘
              ▼
  engine/timeline.py  →  FrameState (camera + characters + facilities + subtitle)
              │
              ▼
  engine/compositor.py  +  engine/camera.py  +  engine/text_renderer.py
              │
              ▼
         PNG frames  →  encoder.py (ffmpeg)  →  MP4
```

### Package Structure

| Module | Role |
|---|---|
| `rawstage/parser/xml_parser.py` | lxml-based XML → `Script` dataclass. Validates asset refs, event attributes, structural rules. |
| `rawstage/parser/models.py` | All dataclasses: `Script`, `Scene`, `Transition`, event types, `Assets` (characters, facilities, expressions, audios), `Hole`, `EnterHoleEvent`, runtime `FrameState`/`CharacterState`/`FacilityState`/`CameraState`/`HoleState`. |
| `rawstage/engine/timeline.py` | Resolves `FrameState` for any time `t` within a scene: evaluates enter/exit/move/camera/dialogue/expression/enter_hole events in priority order. Hole resolution (step 3) sits between position and camera. |
| `rawstage/engine/compositor.py` | Composites a single frame: groups facilities + characters by `layer` → sorts layers alphabetically → sorts by `z` within layer → canvas→screen transform → hole covers → hole visual re-draw → subtitle on top. |
| `rawstage/engine/camera.py` | `canvas_to_screen()` / `screen_to_canvas()` transform with camera scale + pan. |
| `rawstage/engine/easing.py` | Quadratic easing functions: `linear`, `ease_in`, `ease_out`, `ease_in_out`. |
| `rawstage/engine/text_renderer.py` | Rich-text subtitle rendering with per-span styling (color, size, italic, bold, underline, outline). CJK font auto-detection. |
| `rawstage/renderer.py` | Full-script orchestration: builds global timeline from interleaved Scene+Transition blocks, renders every frame, handles cross-scene transitions (fade, dissolve, wipe). |
| `rawstage/encoder.py` | ffmpeg wrapper: two paths — `encode_video` (PNG sequence → MP4, legacy) and `encode_video_pipe` (raw RGB via stdin pipe, no temp files). Supports audio mixing (delay, trim, volume, loop). |
| `rawstage/asset_loader.py` | Simple image cache (`load_image` / `clear_cache`). |
| `rawstage/__main__.py` | Entry point for `python -m rawstage`. Delegates to `cli.main()`. |
| `rawstage/cli.py` | argparse-based CLI with `render`, `frame`, `animate` subcommands. Progress bar via tqdm (`--progress`). |
| `rawstage/errors.py` | Exception hierarchy: `RawStageError` → `ParseError`, `AssetError`, `RenderError`. |

### Key Design Decisions

- **1920×1080 canvas**; character anchor point is bottom-center (feet).
- **Layer + z-index** rendering: each asset has `layer` (string) and `z` (int 0-200). Layers sorted alphabetically, z ascending within layer. Higher z = closer to viewer.
- **Facilities** are static props/backgrounds (`<facility>` tag), placed per scene via `<initial_facilities>`. No separate `<background>` asset type.
- **Absolute timeline** per scene (starts at 0s), all events driven by `start` + `duration`.
- **Camera model**: viewport defined by `center_x, center_y` + `scale` (1.0 = full canvas). Characters rendered larger/smaller via camera scale, not individual scaling.
- **Character z-sort removed** — now replaced by explicit `layer` + `z` system that covers both characters and facilities.
- **Event priority in timeline resolution**: expressions → visibility/position → holes → camera → subtitle. This order avoids circular dependencies.
- **Hole system**: `<hole>` scene element defines a ground opening at (x, y). `<enter_hole>` timeline event activates cover. Cover samples from `sample_facility` and draws from ground level (hole.y) **downward** to the character's feet — creating a "sinking into ground" effect where the character physically descends (via move events) and the ground naturally clips them. `depth_ratio` only controls cover activation, not cover height. `visual_facility` is re-drawn after covers to keep the hole opening visible. Hole states use compound key `(character_id, hole_id)`. Pairs with an `enter_hole` event are excluded from passive detection to prevent depth_ratio discontinuities.
- **Enter/exit animations**: characters offset off-screen during slide/fade, no separate "off-screen" tracking.
- **Transitions**: scenes overlap during transition duration; `_build_timeline()` in renderer.py handles the overlapping timeline math.
- **Pipe encoding default**: frames streamed as raw RGB via ffmpeg stdin pipe — no temp PNG files on disk. Pass `--keep-frames` for the legacy file-based path (useful for debugging).
- **Tests** use XML fixtures in `tests/fixtures/`: `minimal.xml`, `sample.xml`, `two_scene.xml`, `rich_text.xml`, `story_demo.xml`.

### Adding a New XML Event Type

1. Add dataclass in `parser/models.py` extending `TimelineEvent`.
2. Add parsing in `xml_parser.py` `_parse_timeline()`.
3. Handle in `engine/timeline.py` `evaluate_timeline()` — add resolution logic and a new step if it introduces dependencies.
4. Wire into `FrameState` or `CharacterState` if it produces runtime data.
5. Update `composite_frame()` if it affects rendering.
