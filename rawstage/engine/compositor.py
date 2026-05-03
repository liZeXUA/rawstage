from PIL import Image

from rawstage.parser.models import Scene, FrameState, CameraState, CharacterState
from rawstage.engine.camera import canvas_to_screen
from rawstage.engine.text_renderer import render_subtitle


CANVAS_W = 1920
CANVAS_H = 1080


def composite_frame(bg_image: Image.Image,
                    char_images: dict[str, Image.Image],
                    expr_images: dict[str, Image.Image],
                    state: FrameState) -> Image.Image:
    frame = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 255))

    # 1. Background
    bg = resize_to_fill(bg_image, CANVAS_W, CANVAS_H)
    frame.paste(bg, (0, 0))

    # 2. Characters sorted by canvas y (higher y = closer to viewer)
    visible = [c for c in state.characters.values() if c.visible]
    visible.sort(key=lambda c: c.y)

    for char_state in visible:
        sprite = _get_sprite(char_state.sprite_key, char_images, expr_images)
        if sprite is None:
            continue

        screen_x, screen_y = canvas_to_screen(
            char_state.x, char_state.y, state.camera, CANVAS_W, CANVAS_H)
        total_scale = state.camera.scale * char_state.scale
        new_w = max(1, int(sprite.width * total_scale))
        new_h = max(1, int(sprite.height * total_scale))

        resized = sprite.resize((new_w, new_h), Image.LANCZOS)

        if char_state.opacity < 1.0 and resized.mode == "RGBA":
            alpha = resized.getchannel("A")
            alpha = alpha.point(lambda a: int(a * char_state.opacity))
            resized.putalpha(alpha)

        paste_x = int(screen_x - new_w / 2)
        paste_y = int(screen_y - new_h)

        if _is_visible(paste_x, paste_y, new_w, new_h):
            frame.paste(
                resized, (paste_x, paste_y),
                resized if resized.mode == "RGBA" else None)

    # 3. Subtitle (screen-space, fixed at bottom center)
    if state.subtitle_text:
        sub_img = render_subtitle(state.subtitle_text, CANVAS_W, CANVAS_H)
        sub_x = (CANVAS_W - sub_img.width) // 2
        sub_y = CANVAS_H - sub_img.height - 60
        frame.paste(sub_img, (sub_x, sub_y), sub_img)

    return frame


def composite_static_frame(scene: Scene,
                           bg_image: Image.Image,
                           char_images: dict[str, Image.Image]) -> Image.Image:
    """Render the initial state of a scene (no animation, one frame)."""
    camera = CameraState(
        center_x=scene.initial_camera.center_x,
        center_y=scene.initial_camera.center_y,
        scale=scene.initial_camera.scale,
    )

    characters: dict[str, CharacterState] = {}
    for place in scene.initial_characters:
        characters[place.character] = CharacterState(
            character_id=place.character,
            visible=True,
            x=place.x,
            y=place.y,
            opacity=1.0,
            scale=1.0,
            sprite_key=place.character,
        )

    state = FrameState(camera=camera, characters=characters)
    return composite_frame(bg_image, char_images, {}, state)


def _get_sprite(key: str, char_images: dict[str, Image.Image],
                expr_images: dict[str, Image.Image]) -> Image.Image | None:
    if key in expr_images:
        return expr_images[key]
    return char_images.get(key)


def resize_to_fill(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Scale image to cover target dimensions, center-cropping if aspect differs."""
    img_ratio = img.width / img.height
    target_ratio = target_w / target_h

    if img_ratio > target_ratio:
        new_h = target_h
        new_w = int(target_h * img_ratio)
    else:
        new_w = target_w
        new_h = int(target_w / img_ratio)

    resized = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _is_visible(x: int, y: int, w: int, h: int) -> bool:
    return (x + w > 0 and x < CANVAS_W and y + h > 0 and y < CANVAS_H)
