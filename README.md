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
| `dialogue` | character, text, start, duration, font, font_size, color, outline_width, outline_color, `<span>` children |
| `expression` | character, set (expression asset id), start |
| `audio` | ref, action (play/play_once), loop, volume, start |
| `transition` | type (fade/dissolve/wipe_left/wipe_right), duration |

### Subtitle styling

`<dialogue>` supports two forms:

**Plain text** (backward compatible) — all text in a single `text` attribute:

```xml
<dialogue character="alice" start="4.5" duration="2.5"
          text="你好，今天天气真好！" />
```

**Rich text** — use `<span>` children for mixed styles within one subtitle line:

```xml
<dialogue character="alice" start="3.0" duration="3.0"
          font_size="48" color="#FFFFFF"
          outline_width="2" outline_color="#333333">
  <span color="#00FF00" italic="true">绿色斜体，</span>
  <span color="#FF0000" underline="true" bold="true">红色粗体下划线</span>
</dialogue>
```

Dialogue-level attributes serve as defaults for all spans:

| Attribute | Default | Description |
|-----------|---------|-------------|
| `font` | (system CJK font) | Font file path |
| `font_size` | 40 | Default font size in pixels |
| `color` | `#FFFFFF` | Default text color (hex RGB / RGBA) |
| `outline_width` | 3 | Outline thickness in pixels |
| `outline_color` | `#000000` | Outline color (hex RGB / RGBA) |

Each `<span>` can override:

| Attribute | Description |
|-----------|-------------|
| `color` | Text color (hex, e.g. `#FF0000`) |
| `size` | Font size override |
| `italic` | `"true"` / `"false"` |
| `underline` | `"true"` / `"false"` |
| `bold` | `"true"` / `"false"` |
| `font` | Font file path override |

Spans are concatenated horizontally with baseline alignment. If no `<span>` children are present, the `text` attribute is rendered as a single span using dialogue-level defaults.

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
