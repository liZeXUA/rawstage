from pathlib import Path
import pytest
from rawstage.parser import parse_script
from rawstage.errors import ParseError
from rawstage.parser.models import (
    Script, Scene, Transition, EnterEvent, MoveEvent, RotateEvent, CameraEvent,
    DialogueEvent, ExpressionEvent, ExitEvent, AudioEvent, DialogueSpan,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_minimal():
    script = parse_script(FIXTURES / "minimal.xml")
    assert script.meta["title"] == "Minimal Test"
    assert "alice" in script.assets.characters
    assert "bg_park" in script.assets.facilities
    assert len(script.blocks) == 1
    scene = script.blocks[0]
    assert isinstance(scene, Scene)
    assert scene.id == "1"
    assert scene.duration == 5.0
    assert len(scene.initial_characters) == 1
    assert scene.initial_characters[0].character == "alice"
    assert scene.initial_characters[0].x == 400
    assert scene.initial_characters[0].y == 800
    assert len(scene.initial_facilities) == 1
    assert scene.initial_facilities[0].facility == "bg_park"
    assert scene.initial_camera.center_x == 960
    assert scene.initial_camera.scale == 1.0


def test_parse_sample():
    script = parse_script(FIXTURES / "sample.xml")
    assert script.meta["title"] == "公园初遇"
    assert len(script.assets.characters) == 2
    assert "alice_shy" in script.assets.expressions
    assert "park" in script.assets.facilities
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


def test_parse_rich_text():
    script = parse_script(FIXTURES / "rich_text.xml")
    scene = script.blocks[0]
    events = scene.events

    # First dialogue: plain text (backward compat)
    d0 = events[0]
    assert isinstance(d0, DialogueEvent)
    assert d0.text == "普通的白色字幕"
    assert d0.spans is None
    assert d0.font_size == 40
    assert d0.color == "#FFFFFF"

    # Second dialogue: mixed styles
    d1 = events[1]
    assert isinstance(d1, DialogueEvent)
    assert d1.font_size == 48
    assert d1.outline_width == 2
    assert d1.outline_color == "#333333"
    assert d1.spans is not None
    assert len(d1.spans) == 2
    assert d1.spans[0].text == "绿色斜体，"
    assert d1.spans[0].color == "#00FF00"
    assert d1.spans[0].italic is True
    assert d1.spans[1].text == "红色粗体下划线"
    assert d1.spans[1].color == "#FF0000"
    assert d1.spans[1].underline is True
    assert d1.spans[1].bold is True

    # Third dialogue: per-span font sizes
    d2 = events[2]
    assert isinstance(d2, DialogueEvent)
    assert d2.color == "#FFFF00"
    assert d2.spans is not None
    assert len(d2.spans) == 2
    assert d2.spans[0].size == 36
    assert d2.spans[0].text == "小字，"
    assert d2.spans[1].size == 60
    assert d2.spans[1].color == "#00BFFF"


def test_rich_text_span_defaults():
    """Span without explicit styles inherits dialogue defaults."""
    script = parse_script(FIXTURES / "rich_text.xml")
    scene = script.blocks[0]
    d2 = scene.events[2]
    span0 = d2.spans[0]
    assert span0.italic is False
    assert span0.underline is False
    assert span0.bold is False
    assert span0.font is None


def test_facility_layer_z():
    script = parse_script(FIXTURES / "minimal.xml")
    fac = script.assets.facilities["bg_park"]
    assert fac.layer == "background"
    assert fac.z == 0


def test_character_layer_z():
    script = parse_script(FIXTURES / "sample.xml")
    alice = script.assets.characters["alice"]
    assert alice.layer == "platform"
    assert alice.z == 100
    bob = script.assets.characters["bob"]
    assert bob.z == 110


def test_parse_facility_move():
    script = parse_script(FIXTURES / "facility_move.xml")
    scene = script.blocks[0]
    moves = [e for e in scene.events if isinstance(e, MoveEvent)]
    # First move: facility linear move
    fm = [m for m in moves if m.facility == "tree_left"]
    assert len(fm) == 2
    assert fm[0].character == ""
    assert fm[0].to_x == 900
    assert fm[0].to_y == 300
    assert fm[0].easing == "linear"
    # Second: facility path move
    assert fm[1].path is not None
    assert len(fm[1].path) == 3
    assert fm[1].path[0] == (900, 300)


def test_move_mutual_exclusive():
    """move with both character and facility should raise ParseError."""
    from lxml import etree
    raw = """<?xml version="1.0"?>
    <comic_script version="1.0">
      <assets>
        <character id="a" src="x.png" layer="platform" z="100" />
        <facility id="f" src="x.png" layer="midground" z="50" />
      </assets>
      <scene id="1" duration="5">
        <initial_camera />
        <initial_characters />
        <initial_facilities />
        <timeline>
          <move character="a" facility="f" to_x="100" start="0" duration="2" />
        </timeline>
      </scene>
    </comic_script>"""
    from pathlib import Path
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
        f.write(raw)
        tmp = Path(f.name)
    try:
        with pytest.raises(ParseError, match="both character and facility"):
            parse_script(tmp)
    finally:
        tmp.unlink()


class TestRotateParser:
    """Tests for <rotate> event parsing."""

    def test_parse_rotate_character(self):
        script = parse_script(FIXTURES / "facility_move.xml")
        scene = script.blocks[0]
        rotates = [e for e in scene.events if isinstance(e, RotateEvent)]
        rc = [r for r in rotates if r.character == "b"]
        assert len(rc) == 1
        assert rc[0].to_angle == 360
        assert rc[0].easing == "linear"
        assert rc[0].start == 1.0
        assert rc[0].duration == 2.0

    def test_parse_rotate_facility(self):
        script = parse_script(FIXTURES / "facility_move.xml")
        scene = script.blocks[0]
        rotates = [e for e in scene.events if isinstance(e, RotateEvent)]
        rf = [r for r in rotates if r.facility == "tree_left"]
        assert len(rf) == 1
        assert rf[0].to_angle == 90
        assert rf[0].anchor_character == "b"
        assert rf[0].easing == "ease_in_out"

    def test_rotate_with_fixed_anchor(self):
        raw = """<?xml version="1.0"?>
        <comic_script version="1.0">
          <assets>
            <character id="a" src="x.png" layer="platform" z="100" />
          </assets>
          <scene id="1" duration="5">
            <initial_camera />
            <initial_characters />
            <initial_facilities />
            <timeline>
              <rotate character="a" to_angle="180"
                      anchor_x="960" anchor_y="540"
                      start="1.0" duration="2.0" />
            </timeline>
          </scene>
        </comic_script>"""
        import tempfile
        from pathlib import Path
        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write(raw)
            tmp = Path(f.name)
        try:
            script = parse_script(tmp)
            event = script.blocks[0].events[0]
            assert isinstance(event, RotateEvent)
            assert event.anchor_x == 960.0
            assert event.anchor_y == 540.0
            assert event.anchor_character == ""
            assert event.anchor_facility == ""
        finally:
            tmp.unlink()

    def test_rotate_mutual_exclusive(self):
        """rotate with both character and facility should raise ParseError."""
        raw = """<?xml version="1.0"?>
        <comic_script version="1.0">
          <assets>
            <character id="a" src="x.png" layer="platform" z="100" />
            <facility id="f" src="x.png" layer="midground" z="50" />
          </assets>
          <scene id="1" duration="5">
            <initial_camera />
            <initial_characters />
            <initial_facilities />
            <timeline>
              <rotate character="a" facility="f" to_angle="90" start="0" duration="2" />
            </timeline>
          </scene>
        </comic_script>"""
        import tempfile
        from pathlib import Path
        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write(raw)
            tmp = Path(f.name)
        try:
            with pytest.raises(ParseError, match="both character and facility"):
                parse_script(tmp)
        finally:
            tmp.unlink()

    def test_rotate_missing_to_angle(self):
        raw = """<?xml version="1.0"?>
        <comic_script version="1.0">
          <assets>
            <character id="a" src="x.png" layer="platform" z="100" />
          </assets>
          <scene id="1" duration="5">
            <initial_camera />
            <initial_characters />
            <initial_facilities />
            <timeline>
              <rotate character="a" start="0" duration="2" />
            </timeline>
          </scene>
        </comic_script>"""
        import tempfile
        from pathlib import Path
        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write(raw)
            tmp = Path(f.name)
        try:
            with pytest.raises(ParseError, match="to_angle"):
                parse_script(tmp)
        finally:
            tmp.unlink()

    def test_rotate_mixed_anchor(self):
        """Cannot mix fixed anchor coords with entity-bound anchor."""
        raw = """<?xml version="1.0"?>
        <comic_script version="1.0">
          <assets>
            <character id="a" src="x.png" layer="platform" z="100" />
            <character id="b" src="x.png" layer="platform" z="110" />
          </assets>
          <scene id="1" duration="5">
            <initial_camera />
            <initial_characters />
            <initial_facilities />
            <timeline>
              <rotate character="a" to_angle="90" start="0" duration="2"
                      anchor_x="100" anchor_character="b" />
            </timeline>
          </scene>
        </comic_script>"""
        import tempfile
        from pathlib import Path
        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write(raw)
            tmp = Path(f.name)
        try:
            with pytest.raises(ParseError, match="cannot mix"):
                parse_script(tmp)
        finally:
            tmp.unlink()
