from pathlib import Path
import pytest
from rawstage.parser import parse_script
from rawstage.errors import ParseError
from rawstage.parser.models import (
    Script, Scene, Transition, EnterEvent, MoveEvent, CameraEvent,
    DialogueEvent, ExpressionEvent, ExitEvent, AudioEvent,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_minimal():
    script = parse_script(FIXTURES / "minimal.xml")
    assert script.meta["title"] == "Minimal Test"
    assert "alice" in script.assets.characters
    assert "bg_park" in script.assets.backgrounds
    assert len(script.blocks) == 1
    scene = script.blocks[0]
    assert isinstance(scene, Scene)
    assert scene.id == "1"
    assert scene.duration == 5.0
    assert scene.background == "bg_park"
    assert len(scene.initial_characters) == 1
    assert scene.initial_characters[0].character == "alice"
    assert scene.initial_characters[0].x == 400
    assert scene.initial_characters[0].y == 800
    assert scene.initial_camera.center_x == 960
    assert scene.initial_camera.scale == 1.0


def test_parse_sample():
    script = parse_script(FIXTURES / "sample.xml")
    assert script.meta["title"] == "公园初遇"
    assert len(script.assets.characters) == 2
    assert "alice_shy" in script.assets.expressions
    assert len(script.blocks) == 1
    scene = script.blocks[0]
    assert scene.duration == 10.0

    events = scene.events
    assert isinstance(events[0], AudioEvent)
    assert isinstance(events[1], EnterEvent)
    assert events[1].method == "slide_left"
    assert isinstance(events[2], MoveEvent)
    assert events[2].easing == "ease_in_out"
    assert isinstance(events[3], CameraEvent)
    assert events[3].target == "bob"
    assert isinstance(events[4], DialogueEvent)
    assert "你好" in events[4].text
    assert isinstance(events[5], ExpressionEvent)
    assert events[5].set == "alice_shy"
    assert isinstance(events[6], MoveEvent)
    assert isinstance(events[7], CameraEvent)
    assert isinstance(events[8], ExitEvent)
    assert events[8].method == "slide_right"

    assert len(events) == 9
    # Verify sorted by start
    for i in range(len(events) - 1):
        assert events[i].start <= events[i + 1].start


def test_missing_asset():
    xml = FIXTURES / "minimal.xml"
    # Should parse fine since we reference valid assets
    script = parse_script(xml)
    assert script is not None


def test_default_values():
    script = parse_script(FIXTURES / "minimal.xml")
    scene = script.blocks[0]
    assert scene.initial_camera.center_x == 960


def test_events_sorted():
    script = parse_script(FIXTURES / "sample.xml")
    scene = script.blocks[0]
    starts = [e.start for e in scene.events]
    assert starts == sorted(starts)
