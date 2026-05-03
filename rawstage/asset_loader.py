from pathlib import Path
from PIL import Image


_image_cache: dict[str, Image.Image] = {}


def load_image(path: Path) -> Image.Image:
    key = str(path.resolve())
    if key in _image_cache:
        return _image_cache[key]

    if not path.exists():
        raise FileNotFoundError(f"Asset not found: {path}")

    img = Image.open(path).convert("RGBA")
    _image_cache[key] = img
    return img


def clear_cache() -> None:
    _image_cache.clear()
