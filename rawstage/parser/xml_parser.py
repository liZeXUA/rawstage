from pathlib import Path
from lxml import etree

from rawstage.errors import ParseError
from rawstage.parser.models import (
    Assets, CharacterAsset, ExpressionAsset, BackgroundAsset, AudioAsset,
    Scene, Transition, Script,
    InitialCamera, Place,
    EnterEvent, ExitEvent, MoveEvent, CameraEvent, DialogueEvent,
    ExpressionEvent, AudioEvent,
)

VALID_ENTER_METHODS = {"fade_in", "slide_left", "slide_right", "slide_up", "slide_down", "pop_in"}
VALID_EXIT_METHODS = {"fade_out", "slide_left", "slide_right", "slide_up", "slide_down"}
VALID_EASING = {"linear", "ease_in", "ease_out", "ease_in_out"}
VALID_TRANSITION_TYPES = {"fade", "wipe_left", "wipe_right", "dissolve"}


def parse_script(xml_path: Path) -> Script:
    if not xml_path.exists():
        raise ParseError(f"XML file not found: {xml_path}")

    tree = etree.parse(str(xml_path))
    root = tree.getroot()

    if root.tag != "comic_script":
        raise ParseError(f"Root element must be <comic_script>, got <{root.tag}>")

    meta = _parse_meta(root.find("meta"))
    assets = _parse_assets(root.find("assets"))
    blocks = _parse_blocks(root, assets)

    return Script(meta=meta, assets=assets, blocks=blocks)


def _parse_meta(el) -> dict[str, str]:
    if el is None:
        return {}
    return dict(el.attrib)


def _parse_assets(el) -> Assets:
    assets = Assets()
    if el is None:
        return assets

    for child in el:
        tag = child.tag
        attrs = dict(child.attrib)
        asset_id = attrs.pop("id", None)

        if tag == "character":
            assets.characters[asset_id] = CharacterAsset(
                id=asset_id, name=attrs.get("name", asset_id), src=attrs.get("src", ""))
        elif tag == "expression":
            assets.expressions[asset_id] = ExpressionAsset(
                id=asset_id, character=attrs.get("character", ""), src=attrs.get("src", ""))
        elif tag == "background":
            assets.backgrounds[asset_id] = BackgroundAsset(
                id=asset_id, src=attrs.get("src", ""))
        elif tag == "audio":
            assets.audios[asset_id] = AudioAsset(
                id=asset_id, src=attrs.get("src", ""))

    return assets


def _parse_blocks(root, assets: Assets) -> list[Scene | Transition]:
    blocks: list[Scene | Transition] = []
    children = list(root)

    for child in children:
        if child.tag == "scene":
            blocks.append(_parse_scene(child, assets))
        elif child.tag == "transition":
            blocks.append(_parse_transition(child))
        # meta and assets are parsed separately, skip here

    _validate_blocks(blocks)
    return blocks


def _parse_scene(el, assets: Assets) -> Scene:
    scene_id = _require(el, "id")
    background_ref = _require(el, "background")
    duration = float(_require(el, "duration"))

    if background_ref not in assets.backgrounds:
        raise ParseError(
            f"Scene {scene_id}: background '{background_ref}' not declared in <assets>")

    initial_camera = _parse_initial_camera(el.find("initial_camera"))
    initial_characters = _parse_initial_characters(
        el.find("initial_characters"), assets, scene_id)
    events = _parse_timeline(el.find("timeline"), assets, scene_id)

    return Scene(
        id=scene_id,
        background=background_ref,
        duration=duration,
        initial_camera=initial_camera,
        initial_characters=initial_characters,
        events=events,
    )


def _parse_initial_camera(el) -> InitialCamera:
    if el is None:
        return InitialCamera()
    return InitialCamera(
        center_x=float(el.get("center_x", 960)),
        center_y=float(el.get("center_y", 540)),
        scale=float(el.get("scale", 1.0)),
    )


def _parse_initial_characters(el, assets: Assets, scene_id: str) -> list[Place]:
    if el is None:
        return []
    places = []
    for child in el:
        if child.tag != "place":
            continue
        char_id = _require(child, "character")
        if char_id not in assets.characters:
            raise ParseError(
                f"Scene {scene_id}: character '{char_id}' not declared in <assets>")
        places.append(Place(
            character=char_id,
            x=float(_require(child, "x")),
            y=float(_require(child, "y")),
        ))
    return places


def _parse_timeline(el, assets: Assets, scene_id: str) -> list:
    if el is None:
        return []

    events = []
    for child in el:
        tag = child.tag
        attrs = dict(child.attrib)
        start = float(attrs.get("start", 0))
        duration = float(attrs.get("duration", 0))

        if tag == "enter":
            char = attrs.get("character", "")
            _check_character(char, assets, scene_id, "enter")
            method = attrs.get("method", "fade_in")
            if method not in VALID_ENTER_METHODS:
                raise ParseError(f"Scene {scene_id}: invalid enter method '{method}'")
            events.append(EnterEvent(
                start=start, duration=duration, character=char, method=method,
                target_x=float(attrs["target_x"]) if "target_x" in attrs else None,
                target_y=float(attrs["target_y"]) if "target_y" in attrs else None,
            ))

        elif tag == "exit":
            char = attrs.get("character", "")
            _check_character(char, assets, scene_id, "exit")
            method = attrs.get("method", "slide_right")
            if method not in VALID_EXIT_METHODS:
                raise ParseError(f"Scene {scene_id}: invalid exit method '{method}'")
            events.append(ExitEvent(
                start=start, duration=duration, character=char, method=method))

        elif tag == "move":
            char = attrs.get("character", "")
            _check_character(char, assets, scene_id, "move")
            easing = attrs.get("easing", "linear")
            if easing not in VALID_EASING:
                raise ParseError(f"Scene {scene_id}: invalid easing '{easing}'")
            path = None
            if "path" in attrs:
                path = _parse_path(attrs["path"], scene_id)
            events.append(MoveEvent(
                start=start, duration=duration, character=char,
                to_x=float(attrs["to_x"]) if "to_x" in attrs else None,
                to_y=float(attrs["to_y"]) if "to_y" in attrs else None,
                path=path, easing=easing,
            ))

        elif tag == "camera":
            target = attrs.get("target")
            if target:
                _check_character(target, assets, scene_id, "camera")
            easing = attrs.get("easing", "linear")
            if easing not in VALID_EASING:
                raise ParseError(f"Scene {scene_id}: invalid camera easing '{easing}'")
            events.append(CameraEvent(
                start=start, duration=duration,
                target=target,
                center_x=float(attrs["center_x"]) if "center_x" in attrs else None,
                center_y=float(attrs["center_y"]) if "center_y" in attrs else None,
                scale=float(attrs["scale"]) if "scale" in attrs else None,
                easing=easing,
            ))

        elif tag == "dialogue":
            char = attrs.get("character", "")
            _check_character(char, assets, scene_id, "dialogue")
            text = attrs.get("text", "")
            events.append(DialogueEvent(
                start=start, duration=duration, character=char, text=text))

        elif tag == "expression":
            char = attrs.get("character", "")
            _check_character(char, assets, scene_id, "expression")
            expr_id = attrs.get("set", "")
            if expr_id not in assets.expressions:
                raise ParseError(
                    f"Scene {scene_id}: expression '{expr_id}' not declared in <assets>")
            events.append(ExpressionEvent(
                start=start, duration=duration, character=char, set=expr_id))

        elif tag == "audio":
            ref = attrs.get("ref", "")
            if ref not in assets.audios:
                raise ParseError(
                    f"Scene {scene_id}: audio '{ref}' not declared in <assets>")
            action = attrs.get("action", "play")
            if action not in ("play", "play_once"):
                raise ParseError(f"Scene {scene_id}: invalid audio action '{action}'")
            events.append(AudioEvent(
                start=start, duration=duration, ref=ref, action=action,
                loop=attrs.get("loop", "false").lower() == "true",
                volume=float(attrs.get("volume", 1.0)),
            ))

    events.sort(key=lambda e: e.start)
    return events


def _parse_transition(el) -> Transition:
    trans_type = el.get("type", "fade")
    if trans_type not in VALID_TRANSITION_TYPES:
        raise ParseError(f"Invalid transition type '{trans_type}'")
    return Transition(type=trans_type, duration=float(el.get("duration", 0)))


def _parse_path(raw: str, scene_id: str) -> list[tuple[float, float]]:
    points = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        try:
            x_str, y_str = part.split(",", 1)
            points.append((float(x_str.strip()), float(y_str.strip())))
        except ValueError:
            raise ParseError(f"Scene {scene_id}: invalid path point '{part}'")
    if len(points) < 2:
        raise ParseError(f"Scene {scene_id}: path must have at least 2 points")
    return points


def _validate_blocks(blocks: list[Scene | Transition]) -> None:
    if not blocks:
        raise ParseError("Script must contain at least one scene")

    # First block must be a scene
    if isinstance(blocks[0], Transition):
        raise ParseError("Script cannot start with a transition")

    # Last block must be a scene
    if isinstance(blocks[-1], Transition):
        raise ParseError("Script cannot end with a transition")

    # No two transitions in a row
    for i in range(len(blocks) - 1):
        if isinstance(blocks[i], Transition) and isinstance(blocks[i + 1], Transition):
            raise ParseError("Cannot have two consecutive transitions")


def _check_character(char_id: str, assets: Assets, scene_id: str, context: str) -> None:
    if char_id not in assets.characters:
        raise ParseError(
            f"Scene {scene_id}: {context} references unknown character '{char_id}'")


def _require(el, attr: str) -> str:
    val = el.get(attr)
    if val is None:
        raise ParseError(f"Missing required attribute '{attr}' on <{el.tag}>")
    return val
