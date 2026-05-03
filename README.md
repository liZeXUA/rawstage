# RawStage

ComicDirector ML v1.0 rendering engine. Parses XML performance instructions and outputs MP4 video by compositing PNG character sprites and backgrounds.


## Install

```bash
pip install -e .
```

Requires `ffmpeg` on PATH for video encoding.

## Quick start

```bash
# Render a single frame at a given time
rawstage frame scene.xml --assets ./assets/ --time 3.0 --output frame.png

# Render a full PNG frame sequence for a scene
rawstage animate scene.xml --assets ./assets/ --fps 24 --output frames/

# Render a complete script to MP4
rawstage render script.xml --assets ./assets/ --output out.mp4 --fps 24
```

## Supported XML events

| Event | Attributes |
|-------|-----------|
| `enter` | character, method (fade_in/slide_*/pop_in), target_x, target_y, start, duration |
| `exit` | character, method (fade_out/slide_*), start, duration |
| `move` | character, to_x, to_y, path (waypoints), easing, start, duration |
| `camera` | target (character), center_x, center_y, scale, easing, start, duration |
| `dialogue` | character, text, start, duration |
| `expression` | character, set (expression asset id), start |
| `audio` | ref, action (play/play_once), loop, volume, start |
| `transition` | type (fade/dissolve/wipe_left/wipe_right), duration |

## Key design decisions

- **1920×1080 canvas** with unified coordinate system. Character anchor: bottom-center.
- **Absolute timeline** per scene (starts at 0s). All events use `start` (seconds) + `duration`.
- **Camera**: viewport defined by `center_x, center_y` + `scale` (1.0 = full canvas).
- **Character z-sort**: by canvas y (higher = closer). Stable during camera zooms.
- **Quadratic easing** — half the multiplies of cubic, negligible visual difference.
- **Write-then-encode** — never holds more than one frame in memory.
- **No numpy** — Pillow + math covers all needs.

## Running tests

```bash
pytest tests/ -v
```
