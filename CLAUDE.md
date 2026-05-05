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

Requires `ffmpeg` on PATH for video encoding. Dependencies: `Pillow>=10.0`, `lxml>=5.0`. No numpy.

## CLI

```bash
rawstage render script.xml --assets ./assets/ --output out.mp4 --fps 24
rawstage frame scene.xml --assets ./assets/ --time 3.0 --output frame.png
rawstage animate scene.xml --assets ./assets/ --fps 24 --output frames/
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
| `rawstage/parser/models.py` | All dataclasses: `Script`, `Scene`, `Transition`, event types, `Assets` (characters, facilities, expressions, audios), runtime `FrameState`/`CharacterState`/`FacilityState`/`CameraState`. |
| `rawstage/engine/timeline.py` | Resolves `FrameState` for any time `t` within a scene: evaluates enter/exit/move/camera/dialogue/expression events in priority order. |
| `rawstage/engine/compositor.py` | Composites a single frame: groups facilities + characters by `layer` → sorts layers alphabetically → sorts by `z` within layer → canvas→screen transform → subtitle on top. |
| `rawstage/engine/camera.py` | `canvas_to_screen()` / `screen_to_canvas()` transform with camera scale + pan. |
| `rawstage/engine/easing.py` | Quadratic easing functions: `linear`, `ease_in`, `ease_out`, `ease_in_out`. |
| `rawstage/engine/text_renderer.py` | Rich-text subtitle rendering with per-span styling (color, size, italic, bold, underline, outline). CJK font auto-detection. |
| `rawstage/renderer.py` | Full-script orchestration: builds global timeline from interleaved Scene+Transition blocks, renders every frame, handles cross-scene transitions (fade, dissolve, wipe). |
| `rawstage/encoder.py` | ffmpeg wrapper: PNG sequence → MP4, with optional audio mixing (delay, trim, volume, loop). |
| `rawstage/asset_loader.py` | Simple image cache (`load_image` / `clear_cache`). |
| `rawstage/cli.py` | argparse-based CLI with `render`, `frame`, `animate` subcommands. |
| `rawstage/errors.py` | Exception hierarchy: `RawStageError` → `ParseError`, `AssetError`, `RenderError`. |

### Key Design Decisions

- **1920×1080 canvas**; character anchor point is bottom-center (feet).
- **Layer + z-index** rendering: each asset has `layer` (string) and `z` (int 0-200). Layers sorted alphabetically, z ascending within layer. Higher z = closer to viewer.
- **Facilities** are static props/backgrounds (`<facility>` tag), placed per scene via `<initial_facilities>`. No separate `<background>` asset type.
- **Absolute timeline** per scene (starts at 0s), all events driven by `start` + `duration`.
- **Camera model**: viewport defined by `center_x, center_y` + `scale` (1.0 = full canvas). Characters rendered larger/smaller via camera scale, not individual scaling.
- **Character z-sort removed** — now replaced by explicit `layer` + `z` system that covers both characters and facilities.
- **Event priority in timeline resolution**: expressions → visibility/position → camera → subtitle. This order avoids circular dependencies.
- **Enter/exit animations**: characters offset off-screen during slide/fade, no separate "off-screen" tracking.
- **Transitions**: scenes overlap during transition duration; `_build_timeline()` in renderer.py handles the overlapping timeline math.
- **Write-then-encode**: one frame at a time to temp dir, then ffmpeg — never holds multiple frames in memory.
- **Tests** use XML fixtures in `tests/fixtures/`: `minimal.xml`, `sample.xml`, `two_scene.xml`, `rich_text.xml`.

### Adding a New XML Event Type

1. Add dataclass in `parser/models.py` extending `TimelineEvent`.
2. Add parsing in `xml_parser.py` `_parse_timeline()`.
3. Handle in `engine/timeline.py` `evaluate_timeline()` — add resolution logic and a new step if it introduces dependencies.
4. Wire into `FrameState` or `CharacterState` if it produces runtime data.
5. Update `composite_frame()` if it affects rendering.
