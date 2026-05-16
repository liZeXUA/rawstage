from dataclasses import dataclass, field


# ---- Assets ----

@dataclass(slots=True)
class CharacterAsset:
    id: str
    name: str
    src: str
    layer: str = "platform"
    z: int = 100


@dataclass(slots=True)
class ExpressionAsset:
    id: str
    character: str
    src: str


@dataclass(slots=True)
class FacilityAsset:
    id: str
    src: str
    layer: str = "midground"
    z: int = 50


@dataclass(slots=True)
class AudioAsset:
    id: str
    src: str


@dataclass(slots=True)
class Assets:
    characters: dict[str, CharacterAsset] = field(default_factory=dict)
    expressions: dict[str, ExpressionAsset] = field(default_factory=dict)
    facilities: dict[str, FacilityAsset] = field(default_factory=dict)
    audios: dict[str, AudioAsset] = field(default_factory=dict)


# ---- Scene setup ----

@dataclass(slots=True)
class InitialCamera:
    center_x: float = 960.0
    center_y: float = 540.0
    scale: float = 1.0


@dataclass(slots=True)
class Place:
    character: str = ""
    facility: str = ""
    x: float = 0.0
    y: float = 0.0


@dataclass(slots=True)
class Hole:
    id: str
    x: float
    y: float
    width: float
    height: float
    sample_facility: str
    cover_height: float = 60.0
    depth_start: float = 0.0
    depth_end: float = 1.0
    visual_facility: str = ""


# ---- Event types ----

@dataclass(slots=True)
class TimelineEvent:
    start: float
    duration: float


@dataclass(slots=True)
class EnterEvent(TimelineEvent):
    character: str
    method: str  # fade_in, slide_left, slide_right, slide_up, slide_down, pop_in
    target_x: float | None = None
    target_y: float | None = None


@dataclass(slots=True)
class ExitEvent(TimelineEvent):
    character: str
    method: str  # slide_left, slide_right, slide_up, slide_down, fade_out


@dataclass(slots=True)
class MoveEvent(TimelineEvent):
    character: str = ""
    facility: str = ""
    to_x: float | None = None
    to_y: float | None = None
    path: list[tuple[float, float]] | None = None
    easing: str = "linear"


@dataclass(slots=True)
class RotateEvent(TimelineEvent):
    character: str = ""
    facility: str = ""
    to_angle: float = 0.0
    easing: str = "linear"
    anchor_x: float | None = None
    anchor_y: float | None = None
    anchor_character: str = ""
    anchor_facility: str = ""


@dataclass(slots=True)
class CameraEvent(TimelineEvent):
    target: str | None = None
    center_x: float | None = None
    center_y: float | None = None
    scale: float | None = None
    easing: str = "linear"


@dataclass(slots=True)
class DialogueSpan:
    """A styled text segment within a dialogue line."""
    text: str
    color: str | None = None       # hex e.g. "#FF0000"
    size: int | None = None        # font size override
    italic: bool = False
    underline: bool = False
    bold: bool = False
    font: str | None = None        # font file path override


@dataclass(slots=True)
class DialogueEvent(TimelineEvent):
    character: str
    text: str
    spans: list[DialogueSpan] | None = None
    font: str | None = None        # default font file path
    font_size: int = 40
    color: str = "#FFFFFF"         # default hex color
    outline_width: int = 3
    outline_color: str = "#000000"


@dataclass(slots=True)
class ExpressionEvent(TimelineEvent):
    character: str
    set: str  # expression asset id


@dataclass(slots=True)
class EnterHoleEvent(TimelineEvent):
    character: str
    hole: str


@dataclass(slots=True)
class AudioEvent(TimelineEvent):
    ref: str
    action: str  # play, play_once
    loop: bool = False
    volume: float = 1.0


# ---- Top-level containers ----

@dataclass(slots=True)
class Scene:
    id: str
    duration: float
    initial_camera: InitialCamera
    initial_characters: list[Place]
    initial_facilities: list[Place]
    holes: list[Hole]
    events: list[TimelineEvent]


@dataclass(slots=True)
class Transition:
    type: str  # fade, wipe_left, wipe_right, dissolve
    duration: float


@dataclass
class Script:
    meta: dict[str, str]
    assets: Assets
    blocks: list[Scene | Transition]


# ---- Runtime state (engine internal) ----

@dataclass(slots=True)
class CameraState:
    center_x: float = 960.0
    center_y: float = 540.0
    scale: float = 1.0


@dataclass(slots=True)
class CharacterState:
    character_id: str
    visible: bool = False
    x: float = 0.0
    y: float = 0.0
    opacity: float = 1.0
    scale: float = 1.0
    sprite_key: str = ""
    layer: str = "platform"
    z: int = 100
    angle: float = 0.0
    anchor_x: float | None = None
    anchor_y: float | None = None
    anchor_character: str = ""
    anchor_facility: str = ""


@dataclass(slots=True)
class FacilityState:
    facility_id: str
    x: float = 0.0
    y: float = 0.0
    sprite_key: str = ""
    layer: str = "midground"
    z: int = 50
    angle: float = 0.0
    anchor_x: float | None = None
    anchor_y: float | None = None
    anchor_character: str = ""
    anchor_facility: str = ""


@dataclass(slots=True)
class SubtitleSpan:
    """Resolved subtitle span ready for rendering."""
    text: str
    color: tuple[int, int, int, int]  # RGBA
    font_size: int
    italic: bool = False
    underline: bool = False
    bold: bool = False
    font_path: str | None = None


@dataclass(slots=True)
class SubtitleData:
    """Resolved subtitle with styled spans and outline settings."""
    spans: list[SubtitleSpan]
    outline_width: int = 3
    outline_color: tuple[int, int, int, int] = (0, 0, 0, 255)


@dataclass(slots=True)
class HoleState:
    character_id: str
    hole_id: str
    depth_ratio: float = 0.0


@dataclass(slots=True)
class FrameState:
    camera: CameraState = field(default_factory=CameraState)
    characters: dict[str, CharacterState] = field(default_factory=dict)
    facilities: dict[str, FacilityState] = field(default_factory=dict)
    holes: list[Hole] = field(default_factory=list)
    hole_states: dict[tuple[str, str], HoleState] = field(default_factory=dict)
    subtitle: SubtitleData | None = None
