from pathlib import Path
import pytest
from rawstage.parser import parse_script
from rawstage.engine.timeline import evaluate_timeline

FIXTURES = Path(__file__).parent / "fixtures"


def test_timeline_initial_state():
    script = parse_script(FIXTURES / "sample.xml")
    scene = script.blocks[0]

    # t=0: only Alice visible at initial position
    state = evaluate_timeline(scene, script.assets, 0.0)
    assert "alice" in state.characters
    assert state.characters["alice"].visible
    assert state.characters["alice"].x == 400
    assert state.characters["alice"].y == 800
    # Bob not yet entered
    assert "bob" not in state.characters or not state.characters["bob"].visible
    assert state.camera.center_x == 960
    assert state.camera.scale == 1.0


def test_timeline_bob_entered():
    script = parse_script(FIXTURES / "sample.xml")
    scene = script.blocks[0]

    # t=2.0: Bob enter completed (0.5 + 0.8 = 1.3 < 2.0)
    state = evaluate_timeline(scene, script.assets, 2.0)
    assert "bob" in state.characters
    assert state.characters["bob"].visible
    assert state.characters["bob"].x == 1100
    assert state.characters["bob"].y == 800


def test_timeline_bob_moved():
    script = parse_script(FIXTURES / "sample.xml")
    scene = script.blocks[0]

    # t=5.0: move completed (2.0 + 2.0 = 4.0 < 5.0), Bob at target
    state = evaluate_timeline(scene, script.assets, 5.0)
    assert state.characters["bob"].x == 700
    assert state.characters["bob"].y == 800


def test_timeline_camera_tracks_bob():
    script = parse_script(FIXTURES / "sample.xml")
    scene = script.blocks[0]

    # t=5.0: camera event settled, centered on Bob at (700, 800)
    state = evaluate_timeline(scene, script.assets, 5.0)
    assert state.camera.center_x == 700
    assert state.camera.center_y == 800
    assert state.camera.scale == 1.1


def test_timeline_camera_returns():
    script = parse_script(FIXTURES / "sample.xml")
    scene = script.blocks[0]

    # t=10.0: second camera event settled (8.0 + 1.5 = 9.5 < 10.0)
    state = evaluate_timeline(scene, script.assets, 10.0)
    assert state.camera.center_x == 960
    assert state.camera.center_y == 540
    assert state.camera.scale == 1.0


def test_timeline_bob_exited():
    script = parse_script(FIXTURES / "sample.xml")
    scene = script.blocks[0]

    # t=10.0: exit completed (8.5 + 0.8 = 9.3 < 10.0)
    state = evaluate_timeline(scene, script.assets, 10.0)
    assert "bob" not in state.characters or not state.characters["bob"].visible


def test_timeline_dialogue():
    script = parse_script(FIXTURES / "sample.xml")
    scene = script.blocks[0]

    # t=6.0: dialogue active (4.5 to 7.0)
    state = evaluate_timeline(scene, script.assets, 6.0)
    assert state.subtitle is not None
    assert len(state.subtitle.spans) == 1
    assert "你好" in state.subtitle.spans[0].text

    # t=3.0: dialogue not yet started
    state2 = evaluate_timeline(scene, script.assets, 3.0)
    assert state2.subtitle is None


def test_timeline_expression():
    script = parse_script(FIXTURES / "sample.xml")
    scene = script.blocks[0]

    # t=7.0: expression changed (start=6.0)
    state = evaluate_timeline(scene, script.assets, 7.0)
    assert state.characters["alice"].sprite_key == "alice_shy"

    # t=5.0: expression not yet
    state2 = evaluate_timeline(scene, script.assets, 5.0)
    assert state2.characters["alice"].sprite_key == "alice"


def test_ease_in_out_midpoint():
    script = parse_script(FIXTURES / "sample.xml")
    scene = script.blocks[0]

    # t=3.0: move at midpoint (2.0 to 4.0, t=3.0 = 50% progress)
    # With ease_in_out, halfway should be at 50% of path since ease_in_out gives 0.5 at t=0.5
    state = evaluate_timeline(scene, script.assets, 3.0)
    # Bob moving from (1100, 800) to (700, 800)
    assert state.characters["bob"].x == 900  # halfway
    assert state.characters["bob"].y == 800


def test_timeline_move_active():
    script = parse_script(FIXTURES / "sample.xml")
    scene = script.blocks[0]

    # t=2.5: move at 25% progress (but with ease_in_out, eased=2*(0.25)^2=0.125)
    state = evaluate_timeline(scene, script.assets, 2.5)
    # Linear 25% would be 1100 - 400*0.25 = 1000
    # ease_in_out 25%: ease_in_out(0.25) = 2*0.25*0.25 = 0.125
    expected_x = 1100 + (700 - 1100) * 0.125  # 1100 - 50 = 1050
    assert abs(state.characters["bob"].x - expected_x) < 0.1


def test_rich_text_dialogue_spans():
    script = parse_script(FIXTURES / "rich_text.xml")
    scene = script.blocks[0]

    # t=4.5: mixed styles dialogue active (3.0 to 6.0)
    state = evaluate_timeline(scene, script.assets, 4.5)
    assert state.subtitle is not None
    assert len(state.subtitle.spans) == 2

    s0 = state.subtitle.spans[0]
    assert s0.text == "绿色斜体，"
    assert s0.color == (0, 255, 0, 255)    # #00FF00
    assert s0.italic is True
    assert s0.font_size == 48

    s1 = state.subtitle.spans[1]
    assert s1.text == "红色粗体下划线"
    assert s1.color == (255, 0, 0, 255)    # #FF0000
    assert s1.underline is True
    assert s1.bold is True

    assert state.subtitle.outline_width == 2
    assert state.subtitle.outline_color == (51, 51, 51, 255)  # #333333


def test_rich_text_per_span_size():
    script = parse_script(FIXTURES / "rich_text.xml")
    scene = script.blocks[0]

    # t=7.5: per-span font sizes dialogue active (6.5 to 9.0)
    state = evaluate_timeline(scene, script.assets, 7.5)
    assert state.subtitle is not None
    assert len(state.subtitle.spans) == 2
    assert state.subtitle.spans[0].font_size == 36
    assert state.subtitle.spans[0].color == (255, 255, 0, 255)  # #FFFF00 (default)
    assert state.subtitle.spans[1].font_size == 60
    assert state.subtitle.spans[1].color == (0, 191, 255, 255)  # #00BFFF


def test_rich_text_plain_backward_compat():
    script = parse_script(FIXTURES / "rich_text.xml")
    scene = script.blocks[0]

    # t=1.0: plain text dialogue active (0.5 to 2.5)
    state = evaluate_timeline(scene, script.assets, 1.0)
    assert state.subtitle is not None
    assert len(state.subtitle.spans) == 1
    assert state.subtitle.spans[0].text == "普通的白色字幕"
    assert state.subtitle.spans[0].color == (255, 255, 255, 255)
    assert state.subtitle.spans[0].font_size == 40


# ---- Facility move tests ----

def test_facility_move_to():
    script = parse_script(FIXTURES / "facility_move.xml")
    scene = script.blocks[0]

    # t=0: facility at initial position
    state0 = evaluate_timeline(scene, script.assets, 0.0)
    assert state0.facilities["tree_left"].x == 300
    assert state0.facilities["tree_left"].y == 800

    # t=2.0: facility halfway through move (0→4s, linear, 50% progress)
    state = evaluate_timeline(scene, script.assets, 2.0)
    assert state.facilities["tree_left"].x == 600  # 300 + (900-300)*0.5
    assert state.facilities["tree_left"].y == 550  # 800 + (300-800)*0.5

    # t=5.0: move completed, settled at target
    state_end = evaluate_timeline(scene, script.assets, 5.0)
    assert state_end.facilities["tree_left"].x == 900
    assert state_end.facilities["tree_left"].y == 300


def test_facility_move_path():
    script = parse_script(FIXTURES / "facility_move.xml")
    scene = script.blocks[0]

    # t=6.5: path move at 50% (5.0→8.0, t=6.5 = 50% progress)
    # Path: (900,300) → (600,600) → (300,300)
    # Segment lengths: seg1=424.3, seg2=424.3, total=848.5
    # At 50%: end of seg1, at (600, 600)
    state = evaluate_timeline(scene, script.assets, 6.5)
    # ease_in_out at 50% gives 0.5, so exactly at the midpoint of path
    assert abs(state.facilities["tree_left"].x - 600) < 1
    assert abs(state.facilities["tree_left"].y - 600) < 1

    # t=8.0: move completed, settled at last waypoint
    state_end = evaluate_timeline(scene, script.assets, 8.0)
    assert state_end.facilities["tree_left"].x == 300
    assert state_end.facilities["tree_left"].y == 300


# ---- Rotation tests ----

def test_rotate_interpolation():
    """Angle interpolation at event midpoint."""
    script = parse_script(FIXTURES / "facility_move.xml")
    scene = script.blocks[0]

    # char b rotate: start=1.0, duration=2.0, to_angle=360, linear
    # t=2.0 = 50% progress, linear → 180°
    state = evaluate_timeline(scene, script.assets, 2.0)
    assert state.characters["b"].angle == 180.0


def test_rotate_settled():
    """Angle settled at to_angle after event completes."""
    script = parse_script(FIXTURES / "facility_move.xml")
    scene = script.blocks[0]

    # char b rotate: 1.0-3.0, to 360°
    # t=4.0: event completed, angle should be 360°
    state = evaluate_timeline(scene, script.assets, 4.0)
    assert state.characters["b"].angle == 360.0


def test_rotate_facility_anchor():
    """Facility rotate with anchor_character sets correct anchor fields."""
    script = parse_script(FIXTURES / "facility_move.xml")
    scene = script.blocks[0]

    # tree_left rotate: anchor_character="b", start=1.0, duration=3.0, to_angle=90, ease_in_out
    # t=2.0: progress=(2-1)/3=1/3, ease_in_out(1/3)=2*(1/9)=0.222, angle=90*0.222=20°
    state = evaluate_timeline(scene, script.assets, 2.0)
    fac = state.facilities["tree_left"]
    assert fac.angle == pytest.approx(20.0, abs=0.5)
    assert fac.anchor_character == "b"


def test_rotate_move_parallel():
    """Rotation and movement happen simultaneously and independently."""
    script = parse_script(FIXTURES / "facility_move.xml")
    scene = script.blocks[0]

    # t=4.0:
    # - char b rotate (1.0-3.0) completed → angle=360
    # - char b move (3.0-5.0) at 50% → ease_in_out(0.5)=0.5, x=1250, y=700
    state = evaluate_timeline(scene, script.assets, 4.0)
    assert state.characters["b"].angle == 360.0
    assert state.characters["b"].x == 1250.0
    assert state.characters["b"].y == 700.0


def test_rotate_default_anchor():
    """Default anchor is entity's own center (anchor fields empty)."""
    script = parse_script(FIXTURES / "facility_move.xml")
    scene = script.blocks[0]

    # char b rotate: no anchor specified → should default to None/empty
    state = evaluate_timeline(scene, script.assets, 2.0)
    char_b = state.characters["b"]
    assert char_b.anchor_x is None
    assert char_b.anchor_y is None
    assert char_b.anchor_character == ""
    assert char_b.anchor_facility == ""


