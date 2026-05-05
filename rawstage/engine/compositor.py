from PIL import Image

from rawstage.parser.models import (
    Scene, FrameState, CameraState, CharacterState, FacilityState,
)
from rawstage.engine.camera import canvas_to_screen
from rawstage.engine.text_renderer import render_subtitle


CANVAS_W = 1920
CANVAS_H = 1080


class _Drawable:
    """Unified drawable for layer/z sorting."""
    __slots__ = ("x", "y", "layer", "z", "opacity", "scale",
                 "sprite_key", "sprite_width", "sprite_height")

    def __init__(self, x: float, y: float, layer: str, z: int,
                 opacity: float = 1.0, scale: float = 1.0,
                 sprite_key: str = "",
                 sprite_width: int = 0, sprite_height: int = 0):
        self.x = x
        self.y = y
        self.layer = layer
        self.z = z
        self.opacity = opacity
        self.scale = scale
        self.sprite_key = sprite_key
        self.sprite_width = sprite_width
        self.sprite_height = sprite_height


def _pick_filter(sprite: Image.Image) -> int:
    """BILINEAR for large assets (facilities/bg), LANCZOS for small (characters)."""
    if sprite.width >= 500 or sprite.height >= 500:
        return Image.BILINEAR
    return Image.LANCZOS


def _paste_cropped(frame: Image.Image, sprite: Image.Image,
                   total_scale: float, screen_x: float, screen_y: float,
                   opacity: float) -> None:
    """Resize and paste only the visible portion of the sprite onto the frame.

    Computes the paste rectangle in screen space, intersects it with the
    frame bounds, then crops the source sprite accordingly before resizing —
    avoiding wasted upscaling of off-screen regions.
    """
    if total_scale < 0.001:
        return  # entity is effectively invisible (e.g. pop_in at t=0)
    new_w = max(1, int(sprite.width * total_scale))
    new_h = max(1, int(sprite.height * total_scale))
    paste_x = int(screen_x - new_w / 2)
    paste_y = int(screen_y - new_h)

    # Intersection with frame
    clip_left = max(0, paste_x)
    clip_top = max(0, paste_y)
    clip_right = min(CANVAS_W, paste_x + new_w)
    clip_bottom = min(CANVAS_H, paste_y + new_h)

    if clip_left >= clip_right or clip_top >= clip_bottom:
        return

    # Map visible portion back to source image coordinates
    src_x = int((clip_left - paste_x) / total_scale)
    src_y = int((clip_top - paste_y) / total_scale)
    src_w = int((clip_right - clip_left) / total_scale)
    src_h = int((clip_bottom - clip_top) / total_scale)

    # Clamp to image bounds for safety
    src_x = max(0, min(src_x, sprite.width - 1))
    src_y = max(0, min(src_y, sprite.height - 1))
    src_w = max(1, min(src_w, sprite.width - src_x))
    src_h = max(1, min(src_h, sprite.height - src_y))

    cropped = sprite.crop((src_x, src_y, src_x + src_w, src_y + src_h))
    final_w = clip_right - clip_left
    final_h = clip_bottom - clip_top

    resample = _pick_filter(sprite)
    resized = cropped.resize((final_w, final_h), resample)

    if opacity < 1.0 and resized.mode == "RGBA":
        alpha = resized.getchannel("A")
        alpha = alpha.point(lambda a: int(a * opacity))
        resized.putalpha(alpha)

    frame.paste(
        resized, (clip_left, clip_top),
        resized if resized.mode == "RGBA" else None)


def composite_frame(char_images: dict[str, Image.Image],
                    expr_images: dict[str, Image.Image],
                    fac_images: dict[str, Image.Image],
                    state: FrameState) -> Image.Image:
    """Composite a single frame with layer-based rendering.

    1. Collect all drawables (facilities + characters)
    2. Group by layer, sort layers alphabetically
    3. Within each layer, sort by z (ascending, higher z drawn later)
    4. Render each drawable with camera transform
    5. Subtitle always on top (screen-space)
    """
    frame = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 255))

    drawables: list[_Drawable] = []

    # Collect facilities
    for fac_state in state.facilities.values():
        sprite = fac_images.get(fac_state.sprite_key)
        if sprite is None:
            continue
        drawables.append(_Drawable(
            x=fac_state.x,
            y=fac_state.y,
            layer=fac_state.layer,
            z=fac_state.z,
            sprite_key=fac_state.sprite_key,
            sprite_width=sprite.width,
            sprite_height=sprite.height,
        ))

    # Collect visible characters
    for char_state in state.characters.values():
        if not char_state.visible:
            continue
        sprite = _get_sprite(char_state.sprite_key, char_images, expr_images)
        if sprite is None:
            continue
        drawables.append(_Drawable(
            x=char_state.x,
            y=char_state.y,
            layer=char_state.layer,
            z=char_state.z,
            opacity=char_state.opacity,
            scale=char_state.scale,
            sprite_key=char_state.sprite_key,
            sprite_width=sprite.width,
            sprite_height=sprite.height,
        ))

    # Sort: first by layer name, then by z
    drawables.sort(key=lambda d: (d.layer, d.z))

    for d in drawables:
        sprite = (_get_sprite(d.sprite_key, char_images, expr_images)
                  or fac_images.get(d.sprite_key))
        if sprite is None:
            continue

        screen_x, screen_y = canvas_to_screen(
            d.x, d.y, state.camera, CANVAS_W, CANVAS_H)
        total_scale = state.camera.scale * d.scale

        _paste_cropped(frame, sprite, total_scale, screen_x, screen_y, d.opacity)

    # Subtitle (screen-space, fixed at bottom center, always topmost)
    if state.subtitle:
        sub_img = render_subtitle(state.subtitle, CANVAS_W, CANVAS_H)
        sub_x = (CANVAS_W - sub_img.width) // 2
        sub_y = CANVAS_H - sub_img.height - 60
        frame.paste(sub_img, (sub_x, sub_y), sub_img)

    return frame


def composite_static_frame(scene: Scene,
                           char_images: dict[str, Image.Image],
                           fac_images: dict[str, Image.Image]) -> Image.Image:
    """Render the initial state of a scene (no animation, one frame)."""
    camera = CameraState(
        center_x=scene.initial_camera.center_x,
        center_y=scene.initial_camera.center_y,
        scale=scene.initial_camera.scale,
    )

    characters: dict[str, CharacterState] = {}
    for place in scene.initial_characters:
        char_asset_id = place.character
        characters[char_asset_id] = CharacterState(
            character_id=char_asset_id,
            visible=True,
            x=place.x,
            y=place.y,
            opacity=1.0,
            scale=1.0,
            sprite_key=char_asset_id,
        )

    facilities: dict[str, FacilityState] = {}
    for place in scene.initial_facilities:
        facilities[place.facility] = FacilityState(
            facility_id=place.facility,
            x=place.x,
            y=place.y,
            sprite_key=place.facility,
        )

    state = FrameState(camera=camera, characters=characters, facilities=facilities)
    return composite_frame(char_images, {}, fac_images, state)


def _get_sprite(key: str, char_images: dict[str, Image.Image],
                expr_images: dict[str, Image.Image]) -> Image.Image | None:
    if key in expr_images:
        return expr_images[key]
    return char_images.get(key)


def _is_visible(x: int, y: int, w: int, h: int) -> bool:
    return (x + w > 0 and x < CANVAS_W and y + h > 0 and y < CANVAS_H)
