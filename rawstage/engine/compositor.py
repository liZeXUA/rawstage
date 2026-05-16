import math
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
                 "sprite_key", "sprite_width", "sprite_height",
                 "angle", "anchor_x", "anchor_y",
                 "anchor_character", "anchor_facility")

    def __init__(self, x: float, y: float, layer: str, z: int,
                 opacity: float = 1.0, scale: float = 1.0,
                 sprite_key: str = "",
                 sprite_width: int = 0, sprite_height: int = 0,
                 angle: float = 0.0,
                 anchor_x: float | None = None,
                 anchor_y: float | None = None,
                 anchor_character: str = "",
                 anchor_facility: str = ""):
        self.x = x
        self.y = y
        self.layer = layer
        self.z = z
        self.opacity = opacity
        self.scale = scale
        self.sprite_key = sprite_key
        self.sprite_width = sprite_width
        self.sprite_height = sprite_height
        self.angle = angle
        self.anchor_x = anchor_x
        self.anchor_y = anchor_y
        self.anchor_character = anchor_character
        self.anchor_facility = anchor_facility


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


def _resolve_rotation_anchor(
    d: _Drawable,
    state: FrameState,
    sprite: Image.Image,
    char_images: dict[str, Image.Image],
    expr_images: dict[str, Image.Image],
    fac_images: dict[str, Image.Image],
) -> tuple[float, float]:
    """Resolve the rotation anchor to canvas coordinates.

    Priority: entity-bound > fixed coords > default (self center).
    """
    # Entity-bound anchor
    if d.anchor_character:
        anchor_char = state.characters.get(d.anchor_character)
        if anchor_char:
            anchor_sprite = _get_sprite(
                anchor_char.sprite_key, char_images, expr_images)
            if anchor_sprite:
                return anchor_char.x, anchor_char.y - anchor_sprite.height / 2
    if d.anchor_facility:
        anchor_fac = state.facilities.get(d.anchor_facility)
        if anchor_fac:
            anchor_sprite = fac_images.get(anchor_fac.sprite_key)
            if anchor_sprite:
                return anchor_fac.x, anchor_fac.y - anchor_sprite.height / 2

    # Fixed canvas coordinates
    if d.anchor_x is not None and d.anchor_y is not None:
        return d.anchor_x, d.anchor_y

    # Default: entity's own sprite center
    return d.x, d.y - sprite.height / 2


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
            angle=fac_state.angle,
            anchor_x=fac_state.anchor_x,
            anchor_y=fac_state.anchor_y,
            anchor_character=fac_state.anchor_character,
            anchor_facility=fac_state.anchor_facility,
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
            angle=char_state.angle,
            anchor_x=char_state.anchor_x,
            anchor_y=char_state.anchor_y,
            anchor_character=char_state.anchor_character,
            anchor_facility=char_state.anchor_facility,
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

        if d.angle != 0.0:
            # Resolve rotation anchor in canvas coordinates
            anchor_cx, anchor_cy = _resolve_rotation_anchor(
                d, state, sprite, char_images, expr_images, fac_images)

            # Anchor offset from sprite CENTER (in canvas coords).
            # PIL rotates around the sprite center by default, so the
            # offset must be measured from the center, not from feet.
            center_cy = d.y - sprite.height / 2
            dx = anchor_cx - d.x
            dy = anchor_cy - center_cy

            # Rotate sprite around its own center (default PIL behavior).
            # The original center materializes at the center of the expanded image.
            theta = math.radians(d.angle)
            cos_t = math.cos(theta)
            sin_t = math.sin(theta)
            sprite = sprite.rotate(d.angle, resample=Image.BICUBIC, expand=True)

            # After rotation, the original anchor offset rotates too
            rot_dx = dx * cos_t - dy * sin_t
            rot_dy = dx * sin_t + dy * cos_t

            # Anchor screen position
            anchor_sx, anchor_sy = canvas_to_screen(
                anchor_cx, anchor_cy, state.camera, CANVAS_W, CANVAS_H)

            # Virtual bottom-center for _paste_cropped:
            #   screen_x = paste_x + sprite.width/2*total_scale = anchor_sx - rot_dx*total_scale
            #   screen_y = paste_y + sprite.height*total_scale = anchor_sy + (sprite.height/2 - rot_dy)*total_scale
            screen_x = anchor_sx - rot_dx * total_scale
            screen_y = anchor_sy + (sprite.height / 2 - rot_dy) * total_scale

        _paste_cropped(frame, sprite, total_scale, screen_x, screen_y, d.opacity)

    # Hole covers: sample background facility to occlude characters
    _composite_hole_covers(frame, state, fac_images)

    # Subtitle (screen-space, fixed at bottom center, always topmost)
    if state.subtitle:
        sub_img = render_subtitle(state.subtitle, CANVAS_W, CANVAS_H)
        sub_x = (CANVAS_W - sub_img.width) // 2
        sub_y = CANVAS_H - sub_img.height - 60
        frame.paste(sub_img, (sub_x, sub_y), sub_img)

    return frame


def _composite_hole_covers(
    frame: Image.Image,
    state: FrameState,
    fac_images: dict[str, Image.Image],
) -> None:
    """Draw hole cover overlays from sampled background facilities.

    For each active hole state where depth_ratio > depth_start:
    cover from ground level (hole.y) down to the character's feet,
    creating a "sinking into ground" visual. depth_ratio only controls
    cover activation; the cover extent is determined by the character's
    actual position — as the character descends via move events, more
    of their body falls below ground and gets occluded.
    """
    hole_map = {h.id: h for h in state.holes}

    for key, hs in state.hole_states.items():
        hole = hole_map.get(hs.hole_id)
        if hole is None:
            continue
        if hs.depth_ratio <= hole.depth_start:
            continue

        facility_img = fac_images.get(hole.sample_facility)
        if facility_img is None:
            continue

        half_w = hole.width / 2

        # Cover from ground level (hole.y) down to character's feet.
        # The character descends via move events; the cover simply hides
        # everything below the ground line.
        char_state = state.characters.get(hs.character_id)
        char_y = char_state.y if char_state else hole.y
        cover_bottom = max(hole.y, char_y)

        if cover_bottom <= hole.y:
            continue  # Character hasn't descended below ground level

        cover_left = hole.x - half_w
        cover_top = hole.y
        cover_right = hole.x + half_w

        # Map canvas coords to facility image pixels
        fac_state = state.facilities.get(hole.sample_facility)
        if fac_state is None:
            continue
        fac_img_w = facility_img.width
        fac_img_h = facility_img.height
        fac_canvas_left = fac_state.x - fac_img_w / 2
        fac_canvas_top = fac_state.y - fac_img_h

        # Source rectangle in facility image space (float)
        src_left = cover_left - fac_canvas_left
        src_top = cover_top - fac_canvas_top
        src_right = cover_right - fac_canvas_left
        src_bottom = cover_bottom - fac_canvas_top

        # Intersect with image pixel bounds
        src_left_i = max(0, int(src_left))
        src_top_i = max(0, int(src_top))
        src_right_i = min(fac_img_w, max(src_left_i + 1, int(src_right)))
        src_bottom_i = min(fac_img_h, max(src_top_i + 1, int(src_bottom)))

        if src_left_i >= src_right_i or src_top_i >= src_bottom_i:
            continue

        cover_img = facility_img.crop(
            (src_left_i, src_top_i, src_right_i, src_bottom_i))

        # Camera transform: cover rect center-bottom → screen
        cover_center_x = hole.x
        cover_anchor_y = cover_bottom  # bottom of cover rect = hole.y
        screen_x, screen_y = canvas_to_screen(
            cover_center_x, cover_anchor_y,
            state.camera, CANVAS_W, CANVAS_H,
        )

        scale = state.camera.scale
        paste_w = max(1, int(cover_img.width * scale))
        paste_h = max(1, int(cover_img.height * scale))
        paste_x = int(screen_x - paste_w / 2)
        paste_y = int(screen_y - paste_h)

        # Intersect with frame bounds (same pattern as _paste_cropped)
        clip_left = max(0, paste_x)
        clip_top = max(0, paste_y)
        clip_right = min(CANVAS_W, paste_x + paste_w)
        clip_bottom = min(CANVAS_H, paste_y + paste_h)

        if clip_left >= clip_right or clip_top >= clip_bottom:
            continue

        # Re-crop cover_img to visible portion
        sc = scale if scale > 0.001 else 1.0
        src_crop_l = max(0, int((clip_left - paste_x) / sc))
        src_crop_t = max(0, int((clip_top - paste_y) / sc))
        src_crop_r = min(cover_img.width,
                         src_crop_l + max(1, int((clip_right - clip_left) / sc)))
        src_crop_b = min(cover_img.height,
                         src_crop_t + max(1, int((clip_bottom - clip_top) / sc)))

        if src_crop_l >= src_crop_r or src_crop_t >= src_crop_b:
            continue

        cropped = cover_img.crop(
            (src_crop_l, src_crop_t, src_crop_r, src_crop_b))
        resample = _pick_filter(facility_img)
        resized = cropped.resize(
            (clip_right - clip_left, clip_bottom - clip_top), resample)
        frame.paste(
            resized, (clip_left, clip_top),
            resized if resized.mode == "RGBA" else None)

    # Re-draw hole visuals on top of covers so the hole opening stays visible
    _redraw_hole_visuals(frame, state, fac_images)


def _redraw_hole_visuals(
    frame: Image.Image,
    state: FrameState,
    fac_images: dict[str, Image.Image],
) -> None:
    """Re-draw hole visual facilities on top of covers.

    Covers sample from the background and paint over everything including
    the hole visual. Re-drawing the visual facility ensures the hole
    opening remains visible while characters are correctly occluded.
    """
    drawn = set()
    for hole in state.holes:
        if not hole.visual_facility or hole.visual_facility in drawn:
            continue
        fac_state = state.facilities.get(hole.visual_facility)
        if fac_state is None:
            continue
        sprite = fac_images.get(hole.visual_facility)
        if sprite is None:
            continue
        drawn.add(hole.visual_facility)

        screen_x, screen_y = canvas_to_screen(
            fac_state.x, fac_state.y, state.camera, CANVAS_W, CANVAS_H)
        total_scale = state.camera.scale
        _paste_cropped(frame, sprite, total_scale, screen_x, screen_y, 1.0)


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
