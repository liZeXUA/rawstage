from rawstage.parser.models import CameraState


def canvas_to_screen(cx: float, cy: float, camera: CameraState,
                     output_w: int = 1920, output_h: int = 1080) -> tuple[float, float]:
    """Transform a canvas coordinate to screen pixel coordinate.

    Canvas is 1920x1080 virtual space. The camera defines a viewport onto it.
    scale=1.0 means the full canvas is visible.
    """
    sx = (cx - camera.center_x) * camera.scale + output_w / 2
    sy = (cy - camera.center_y) * camera.scale + output_h / 2
    return sx, sy


def screen_to_canvas(sx: float, sy: float, camera: CameraState,
                     output_w: int = 1920, output_h: int = 1080) -> tuple[float, float]:
    """Inverse of canvas_to_screen."""
    cx = (sx - output_w / 2) / camera.scale + camera.center_x
    cy = (sy - output_h / 2) / camera.scale + camera.center_y
    return cx, cy
