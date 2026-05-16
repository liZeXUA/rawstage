from pathlib import Path
from lxml import etree

from rawstage.errors import ParseError
from rawstage.parser.models import (
    Assets, CharacterAsset, ExpressionAsset, FacilityAsset, AudioAsset,
    Scene, Transition, Script,
    InitialCamera, Place, Hole,
    EnterEvent, ExitEvent, MoveEvent, RotateEvent, CameraEvent, DialogueEvent,
    ExpressionEvent, AudioEvent, EnterHoleEvent, DialogueSpan,
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
            layer = attrs.pop("layer", "platform")
            z = int(attrs.pop("z", 100))
            _validate_z(z, asset_id)
            assets.characters[asset_id] = CharacterAsset(
                id=asset_id, name=attrs.get("name", asset_id),
                src=attrs.get("src", ""), layer=layer, z=z)
        elif tag == "expression":
            assets.expressions[asset_id] = ExpressionAsset(
                id=asset_id, character=attrs.get("character", ""), src=attrs.get("src", ""))
        elif tag == "facility":
            layer = attrs.pop("layer", "midground")
            z = int(attrs.pop("z", 50))
            _validate_z(z, asset_id)
            assets.facilities[asset_id] = FacilityAsset(
                id=asset_id, src=attrs.get("src", ""), layer=layer, z=z)
        elif tag == "audio":
            assets.audios[asset_id] = AudioAsset(
                id=asset_id, src=attrs.get("src", ""))

    return assets


def _validate_z(z: int, asset_id: str) -> None:
    if not 0 <= z <= 200:
        raise ParseError(f"Asset '{asset_id}': z must be 0-200, got {z}")


def _parse_blocks(root, assets: Assets) -> list[Scene | Transition]:
    blocks: list[Scene | Transition] = []
    children = list(root)

    for child in children:
        if child.tag == "scene":
            blocks.append(_parse_scene(child, assets))
        elif child.tag == "transition":
            blocks.append(_parse_transition(child))

    _validate_blocks(blocks)
    return blocks


def _parse_scene(el, assets: Assets) -> Scene:
    scene_id = _require(el, "id")
    duration = float(_require(el, "duration"))

    initial_camera = _parse_initial_camera(el.find("initial_camera"))
    initial_characters = _parse_initial_places(
        el.find("initial_characters"), assets, scene_id, "character")
    initial_facilities = _parse_initial_places(
        el.find("initial_facilities"), assets, scene_id, "facility")
    holes = _parse_holes(el.find("holes"), assets, scene_id)
    events = _parse_timeline(el.find("timeline"), assets, scene_id)

    return Scene(
        id=scene_id,
        duration=duration,
        initial_camera=initial_camera,
        initial_characters=initial_characters,
        initial_facilities=initial_facilities,
        holes=holes,
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


def _parse_holes(el, assets: Assets, scene_id: str) -> list[Hole]:
    if el is None:
        return []
    holes = []
    for child in el:
        if child.tag != "hole":
            continue
        hole_id = _require(child, "id")
        sample_fac = _require(child, "sample_facility")
        if sample_fac not in assets.facilities:
            raise ParseError(
                f"Scene {scene_id}: hole '{hole_id}' sample_facility "
                f"'{sample_fac}' not declared in <assets>")
        visual_fac = child.get("visual_facility", "")
        if visual_fac and visual_fac not in assets.facilities:
            raise ParseError(
                f"Scene {scene_id}: hole '{hole_id}' visual_facility "
                f"'{visual_fac}' not declared in <assets>")
        holes.append(Hole(
            id=hole_id,
            x=float(_require(child, "x")),
            y=float(_require(child, "y")),
            width=float(_require(child, "width")),
            height=float(_require(child, "height")),
            sample_facility=sample_fac,
            cover_height=float(child.get("cover_height", 60)),
            depth_start=float(child.get("depth_start", 0)),
            depth_end=float(child.get("depth_end", 1)),
            visual_facility=visual_fac,
        ))
    return holes


def _parse_initial_places(el, assets: Assets, scene_id: str,
                          kind: str) -> list[Place]:
    """Parse <place> children from an initial_characters or initial_facilities element.

    kind: "character" or "facility"
    """
    if el is None:
        return []
    places = []
    for child in el:
        if child.tag != "place":
            continue
        if kind == "character":
            char_id = _require(child, "character")
            if char_id not in assets.characters:
                raise ParseError(
                    f"Scene {scene_id}: character '{char_id}' not declared in <assets>")
            places.append(Place(
                character=char_id,
                x=float(_require(child, "x")),
                y=float(_require(child, "y")),
            ))
        elif kind == "facility":
            fac_id = _require(child, "facility")
            if fac_id not in assets.facilities:
                raise ParseError(
                    f"Scene {scene_id}: facility '{fac_id}' not declared in <assets>")
            places.append(Place(
                facility=fac_id,
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
            fac = attrs.get("facility", "")
            if char and fac:
                raise ParseError(
                    f"Scene {scene_id}: <move> cannot have both character and facility")
            if not char and not fac:
                raise ParseError(
                    f"Scene {scene_id}: <move> must have character or facility")
            if char:
                _check_character(char, assets, scene_id, "move")
            if fac:
                _check_facility(fac, assets, scene_id, "move")
            easing = attrs.get("easing", "linear")
            if easing not in VALID_EASING:
                raise ParseError(f"Scene {scene_id}: invalid easing '{easing}'")
            path = None
            if "path" in attrs:
                path = _parse_path(attrs["path"], scene_id)
            events.append(MoveEvent(
                start=start, duration=duration, character=char, facility=fac,
                to_x=float(attrs["to_x"]) if "to_x" in attrs else None,
                to_y=float(attrs["to_y"]) if "to_y" in attrs else None,
                path=path, easing=easing,
            ))

        elif tag == "rotate":
            char = attrs.get("character", "")
            fac = attrs.get("facility", "")
            if char and fac:
                raise ParseError(
                    f"Scene {scene_id}: <rotate> cannot have both character and facility")
            if not char and not fac:
                raise ParseError(
                    f"Scene {scene_id}: <rotate> must have character or facility")
            if char:
                _check_character(char, assets, scene_id, "rotate")
            if fac:
                _check_facility(fac, assets, scene_id, "rotate")
            to_angle_str = attrs.get("to_angle")
            if to_angle_str is None:
                raise ParseError(
                    f"Scene {scene_id}: <rotate> requires to_angle attribute")
            to_angle = float(to_angle_str)
            easing = attrs.get("easing", "linear")
            if easing not in VALID_EASING:
                raise ParseError(
                    f"Scene {scene_id}: invalid rotate easing '{easing}'")

            # Anchor: at most one mode (fixed coords vs entity-bound)
            anchor_x_str = attrs.get("anchor_x")
            anchor_y_str = attrs.get("anchor_y")
            anchor_char = attrs.get("anchor_character", "")
            anchor_fac = attrs.get("anchor_facility", "")

            has_fixed = anchor_x_str is not None or anchor_y_str is not None
            has_bound = bool(anchor_char) or bool(anchor_fac)
            if has_fixed and has_bound:
                raise ParseError(
                    f"Scene {scene_id}: <rotate> cannot mix fixed anchor coords "
                    f"with anchor_character/anchor_facility")
            if anchor_char:
                _check_character(anchor_char, assets, scene_id, "rotate anchor")
            if anchor_fac:
                _check_facility(anchor_fac, assets, scene_id, "rotate anchor")

            events.append(RotateEvent(
                start=start, duration=duration,
                character=char, facility=fac,
                to_angle=to_angle, easing=easing,
                anchor_x=float(anchor_x_str) if anchor_x_str is not None else None,
                anchor_y=float(anchor_y_str) if anchor_y_str is not None else None,
                anchor_character=anchor_char,
                anchor_facility=anchor_fac,
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
            font = attrs.get("font") or None
            font_size = int(attrs.get("font_size", 40))
            color = attrs.get("color", "#FFFFFF")
            outline_width = int(attrs.get("outline_width", 3))
            outline_color = attrs.get("outline_color", "#000000")

            spans: list[DialogueSpan] | None = None
            span_children = list(child)
            if span_children:
                spans = []
                for span_el in span_children:
                    if span_el.tag != "span":
                        continue
                    spans.append(DialogueSpan(
                        text=span_el.text or "",
                        color=span_el.get("color") or None,
                        size=int(span_el.get("size")) if span_el.get("size") else None,
                        italic=span_el.get("italic", "false").lower() == "true",
                        underline=span_el.get("underline", "false").lower() == "true",
                        bold=span_el.get("bold", "false").lower() == "true",
                        font=span_el.get("font") or None,
                    ))
                if not spans:
                    spans = None

            events.append(DialogueEvent(
                start=start, duration=duration, character=char, text=text,
                spans=spans, font=font, font_size=font_size, color=color,
                outline_width=outline_width, outline_color=outline_color))

        elif tag == "expression":
            char = attrs.get("character", "")
            _check_character(char, assets, scene_id, "expression")
            expr_id = attrs.get("set", "")
            if expr_id not in assets.expressions:
                raise ParseError(
                    f"Scene {scene_id}: expression '{expr_id}' not declared in <assets>")
            events.append(ExpressionEvent(
                start=start, duration=duration, character=char, set=expr_id))

        elif tag == "enter_hole":
            char = attrs.get("character", "")
            _check_character(char, assets, scene_id, "enter_hole")
            hole = attrs.get("hole", "")
            events.append(EnterHoleEvent(
                start=start, duration=duration, character=char, hole=hole))

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

    if isinstance(blocks[0], Transition):
        raise ParseError("Script cannot start with a transition")

    if isinstance(blocks[-1], Transition):
        raise ParseError("Script cannot end with a transition")

    for i in range(len(blocks) - 1):
        if isinstance(blocks[i], Transition) and isinstance(blocks[i + 1], Transition):
            raise ParseError("Cannot have two consecutive transitions")


def _check_character(char_id: str, assets: Assets, scene_id: str, context: str) -> None:
    if char_id not in assets.characters:
        raise ParseError(
            f"Scene {scene_id}: {context} references unknown character '{char_id}'")


def _check_facility(fac_id: str, assets: Assets, scene_id: str, context: str) -> None:
    if fac_id not in assets.facilities:
        raise ParseError(
            f"Scene {scene_id}: {context} references unknown facility '{fac_id}'")


def _require(el, attr: str) -> str:
    val = el.get(attr)
    if val is None:
        raise ParseError(f"Missing required attribute '{attr}' on <{el.tag}>")
    return val
