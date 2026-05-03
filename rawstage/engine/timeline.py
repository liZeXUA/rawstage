from math import hypot

from rawstage.parser.models import (
    Scene, Assets, FrameState, CameraState, CharacterState,
    EnterEvent, ExitEvent, MoveEvent, CameraEvent, DialogueEvent, ExpressionEvent,
)
from rawstage.engine.easing import EASING_MAP


def evaluate_timeline(scene: Scene, assets: Assets, t: float) -> FrameState:
    """Compute the full FrameState for a scene at time t (seconds).

    Resolution order (no circular deps):
    1. Character sprite keys (expressions are instantaneous, canvas-independent)
    2. Character visibility + canvas positions (enter/exit/move, all canvas-space)
    3. Camera (may reference character canvas positions)
    4. Subtitle (screen-space, independent of camera)
    """
    camera = CameraState(
        center_x=scene.initial_camera.center_x,
        center_y=scene.initial_camera.center_y,
        scale=scene.initial_camera.scale,
    )

    # Build character initial states from initial_characters
    char_states: dict[str, CharacterState] = {}
    for place in scene.initial_characters:
        char_states[place.character] = CharacterState(
            character_id=place.character,
            visible=True,
            x=place.x,
            y=place.y,
            opacity=1.0,
            scale=1.0,
            sprite_key=place.character,
        )

    # Separate events by type
    enter_events = [e for e in scene.events if isinstance(e, EnterEvent)]
    exit_events = [e for e in scene.events if isinstance(e, ExitEvent)]
    move_events = [e for e in scene.events if isinstance(e, MoveEvent)]
    camera_events = [e for e in scene.events if isinstance(e, CameraEvent)]
    dialogue_events = [e for e in scene.events if isinstance(e, DialogueEvent)]
    expression_events = [e for e in scene.events if isinstance(e, ExpressionEvent)]

    # --- 1. Expressions: most recent completed event changes sprite ---
    for event in expression_events:
        if t >= event.start:
            char_id = event.character
            if char_id not in char_states:
                char_states[char_id] = CharacterState(character_id=char_id, sprite_key=char_id)
            char_states[char_id].sprite_key = event.set

    # --- 2. Visibility + Position ---
    _resolve_visibility(char_states, enter_events, exit_events, t)
    _resolve_positions(char_states, move_events, enter_events, exit_events, t)

    # Remove invisible characters
    visible_chars = {k: v for k, v in char_states.items() if v.visible}

    # --- 3. Camera ---
    _resolve_camera(camera, camera_events, visible_chars, t)

    # --- 4. Dialogue ---
    subtitle = _resolve_dialogue(dialogue_events, assets, t)

    return FrameState(camera=camera, characters=visible_chars, subtitle_text=subtitle)


def _resolve_visibility(
    char_states: dict[str, CharacterState],
    enter_events: list[EnterEvent],
    exit_events: list[ExitEvent],
    t: float,
) -> None:
    """Determine which characters are visible at time t.

    State machine per character:
    - No enter yet: invisible (unless in initial_characters)
    - During enter animation: visible
    - After enter, before exit: visible
    - During exit animation: visible
    - After exit: invisible
    - A later enter can bring the character back.
    """
    all_chars = set(char_states.keys())
    for event in enter_events + exit_events:
        if isinstance(event, EnterEvent):
            all_chars.add(event.character)
        elif isinstance(event, ExitEvent):
            all_chars.add(event.character)

    for char_id in all_chars:
        if char_id not in char_states:
            char_states[char_id] = CharacterState(character_id=char_id, sprite_key=char_id)

        # Collect enter/exit events for this character, sorted by start
        char_events = sorted(
            [e for e in enter_events + exit_events
             if getattr(e, "character", None) == char_id],
            key=lambda e: e.start,
        )

        visible = char_states[char_id].visible  # starts from initial state
        for event in char_events:
            if isinstance(event, EnterEvent):
                if event.start <= t < event.start + event.duration:
                    # During enter animation
                    visible = True
                    break
                elif event.start + event.duration <= t:
                    # Enter fully complete
                    visible = True
                # else: enter hasn't started yet, don't change
            elif isinstance(event, ExitEvent):
                if event.start <= t < event.start + event.duration:
                    # During exit animation
                    visible = True
                    break
                elif event.start + event.duration <= t:
                    # Exit fully complete
                    visible = False
                # else: exit hasn't started yet, current visibility stands

        char_states[char_id].visible = visible


def _resolve_positions(
    char_states: dict[str, CharacterState],
    move_events: list[MoveEvent],
    enter_events: list[EnterEvent],
    exit_events: list[ExitEvent],
    t: float,
) -> None:
    """Compute canvas position for each character at time t.

    Priority at time t:
    1. Active enter animation -> interpolate from off-screen to target
    2. Active exit animation -> interpolate from current to off-screen
    3. Active move animation -> interpolate along path or to target
    4. Settled position (end of last move, or enter target, or initial place)

    We build a settled-position timeline by processing all events chronologically
    and tracking the "at-rest" position between events.
    """
    for char_id, state in char_states.items():
        # Build a sorted list of all position-affecting events for this character
        pos_events = sorted(
            [(e, "enter") for e in enter_events if e.character == char_id] +
            [(e, "exit") for e in exit_events if e.character == char_id] +
            [(e, "move") for e in move_events if e.character == char_id],
            key=lambda x: x[0].start,
        )

        # Track settled position through time
        settled_x, settled_y = state.x, state.y

        for event, etype in pos_events:
            if isinstance(event, EnterEvent):
                target_x = event.target_x if event.target_x is not None else settled_x
                target_y = event.target_y if event.target_y is not None else settled_y

                if event.start <= t < event.start + event.duration:
                    progress = (t - event.start) / event.duration
                    eased = EASING_MAP["linear"](progress)
                    state.x, state.y = _enter_offset(
                        target_x, target_y, event.method, eased)
                    state.opacity = _enter_opacity(event.method, eased)
                    state.scale = _enter_scale(event.method, eased)
                    return  # Don't process further events for this char
                elif event.start + event.duration <= t:
                    settled_x, settled_y = target_x, target_y

            elif isinstance(event, ExitEvent):
                if event.start <= t < event.start + event.duration:
                    progress = (t - event.start) / event.duration
                    eased = EASING_MAP["linear"](progress)
                    state.x, state.y = _exit_offset(
                        settled_x, settled_y, event.method, eased)
                    state.opacity = _exit_opacity(event.method, eased)
                    return
                elif event.start + event.duration <= t:
                    settled_x, settled_y = state.x, state.y
                    # character is now invisible, but position tracking continues

            elif isinstance(event, MoveEvent):
                old_x, old_y = settled_x, settled_y
                # Compute move destination
                if event.path:
                    dest_x, dest_y = event.path[-1]
                else:
                    dest_x = event.to_x if event.to_x is not None else settled_x
                    dest_y = event.to_y if event.to_y is not None else settled_y

                if event.start <= t < event.start + event.duration:
                    progress = (t - event.start) / max(event.duration, 0.001)
                    eased = EASING_MAP[event.easing](progress)
                    if event.path:
                        state.x, state.y = _interpolate_path(event.path, eased)
                    else:
                        state.x = old_x + (dest_x - old_x) * eased
                        state.y = old_y + (dest_y - old_y) * eased
                    return
                elif event.start + event.duration <= t:
                    settled_x, settled_y = dest_x, dest_y

        # No active event: character at settled position
        state.x, state.y = settled_x, settled_y
        state.opacity = 1.0
        state.scale = 1.0


def _resolve_camera(
    camera: CameraState,
    camera_events: list[CameraEvent],
    char_states: dict[str, CharacterState],
    t: float,
) -> None:
    """Compute camera state at time t by processing camera events chronologically.

    Each camera event specifies which properties to change. Unspecified properties
    remain at their previous value. During the event duration, specified properties
    interpolate from the previous state to the target values.
    """
    for event in camera_events:
        if event.start > t:
            break

        # Compute this event's target values
        target_cx = event.center_x
        target_cy = event.center_y
        target_scale = event.scale

        if event.target and event.target in char_states:
            char_state = char_states[event.target]
            target_cx = char_state.x
            target_cy = char_state.y

        # Values to interpolate FROM
        from_cx = camera.center_x
        from_cy = camera.center_y
        from_scale = camera.scale

        if event.start <= t < event.start + event.duration:
            progress = (t - event.start) / max(event.duration, 0.001)
            eased = EASING_MAP[event.easing](progress)

            if target_cx is not None:
                camera.center_x = from_cx + (target_cx - from_cx) * eased
            if target_cy is not None:
                camera.center_y = from_cy + (target_cy - from_cy) * eased
            if target_scale is not None:
                camera.scale = from_scale + (target_scale - from_scale) * eased
            return  # Active camera event: done interpolating

        else:
            # Fully settled: apply target values
            if target_cx is not None:
                camera.center_x = target_cx
            if target_cy is not None:
                camera.center_y = target_cy
            if target_scale is not None:
                camera.scale = target_scale


def _resolve_dialogue(
    dialogue_events: list[DialogueEvent],
    assets: Assets,
    t: float,
) -> str | None:
    """Find active dialogue at time t. Returns formatted subtitle or None."""
    active = [e for e in dialogue_events
              if e.start <= t <= e.start + e.duration]
    if not active:
        return None

    # Take the most recently started one (handles overlapping case)
    event = max(active, key=lambda e: e.start)

    return event.text


# ---- Enter/Exit position helpers ----

SCREEN_W = 1920
SCREEN_H = 1080


def _enter_offset(target_x: float, target_y: float, method: str, t: float
                  ) -> tuple[float, float]:
    """Offset from target position during enter animation. t in [0,1]."""
    if method == "fade_in" or method == "pop_in":
        return target_x, target_y
    # Sliding offsets: character starts offset and moves toward target
    # Offset is in canvas space (will render correctly with camera zoom)
    offset = SCREEN_W  # roughly one screen width in canvas coords at scale 1.0
    oy = SCREEN_H
    if method == "slide_left":
        return target_x - offset + offset * t, target_y
    elif method == "slide_right":
        return target_x + offset - offset * t, target_y
    elif method == "slide_up":
        return target_x, target_y + oy - oy * t
    elif method == "slide_down":
        return target_x, target_y - oy + oy * t
    return target_x, target_y


def _enter_opacity(method: str, t: float) -> float:
    if method == "fade_in":
        return t
    return 1.0


def _enter_scale(method: str, t: float) -> float:
    """Scale factor during enter. pop_in: 0->1 with overshoot."""
    if method == "pop_in":
        # Overshoot: scale peaks at 1.1 then settles to 1.0
        if t < 0.7:
            return t / 0.7 * 1.1
        else:
            return 1.1 - 0.1 * (t - 0.7) / 0.3
    return 1.0


def _exit_offset(from_x: float, from_y: float, method: str, t: float
                 ) -> tuple[float, float]:
    """Offset from starting position during exit animation. t in [0,1]."""
    if method == "fade_out":
        return from_x, from_y
    offset = SCREEN_W
    oy = SCREEN_H
    if method == "slide_left":
        return from_x - offset * t, from_y
    elif method == "slide_right":
        return from_x + offset * t, from_y
    elif method == "slide_up":
        return from_x, from_y - oy * t
    elif method == "slide_down":
        return from_x, from_y + oy * t
    return from_x, from_y


def _exit_opacity(method: str, t: float) -> float:
    if method == "fade_out":
        return 1.0 - t
    return 1.0


# ---- Path interpolation ----

def _interpolate_path(waypoints: list[tuple[float, float]], t: float
                      ) -> tuple[float, float]:
    """Interpolate along piecewise-linear waypoints based on distance.

    t=0: first waypoint, t=1: last waypoint. Equal-distance parameterization.
    """
    if t <= 0:
        return waypoints[0]
    if t >= 1:
        return waypoints[-1]

    segments = [(waypoints[i], waypoints[i+1]) for i in range(len(waypoints) - 1)]
    lengths = [hypot(b[0] - a[0], b[1] - a[1]) for a, b in segments]
    total = sum(lengths)
    if total == 0:
        return waypoints[0]

    target_dist = t * total
    accumulated = 0.0
    for (a, b), seg_len in zip(segments, lengths):
        if accumulated + seg_len >= target_dist:
            seg_t = (target_dist - accumulated) / seg_len if seg_len > 0 else 0.0
            return (a[0] + (b[0] - a[0]) * seg_t,
                    a[1] + (b[1] - a[1]) * seg_t)
        accumulated += seg_len

    return waypoints[-1]
