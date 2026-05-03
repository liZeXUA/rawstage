"""ffmpeg video encoding from PNG frame sequences."""

import subprocess
import shutil
from pathlib import Path

from rawstage.errors import RawStageError


class EncoderError(RawStageError):
    pass


def find_ffmpeg() -> str:
    """Return path to ffmpeg binary, or raise EncoderError."""
    path = shutil.which("ffmpeg")
    if path is None:
        raise EncoderError(
            "ffmpeg not found on PATH. Install ffmpeg to encode video.")
    return path


def encode_video(
    frame_dir: Path,
    output_path: Path,
    fps: int,
    total_frames: int,
    preset: str = "ultrafast",
    audio_inputs: list[tuple[Path, float, float, bool, float]] | None = None,
    start_number: int = 0,
) -> None:
    """Encode a PNG frame sequence to MP4 using ffmpeg.

    Args:
        frame_dir: Directory containing frame_000000.png ... frame_NNNNNN.png
        output_path: Output MP4 file path
        fps: Frames per second
        total_frames: Total number of frames to encode
        preset: x264 preset (ultrafast, medium, etc.)
        audio_inputs: Optional list of (path, start_sec, duration_sec, loop, volume)
        start_number: First frame number (default 0)
    """
    ffmpeg = find_ffmpeg()

    input_pattern = str(frame_dir / "frame_%06d.png")

    cmd = [
        ffmpeg, "-y",
        "-framerate", str(fps),
        "-start_number", str(start_number),
        "-i", input_pattern,
        "-frames:v", str(total_frames),
    ]

    if audio_inputs:
        audio_streams = _build_audio_filter(cmd, audio_inputs, fps, total_frames)
        cmd.extend([
            "-c:v", "libx264",
            "-preset", preset,
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-filter_complex", audio_streams,
            "-map", "0:v:0",
            "-map", "[audio_out]",
            "-shortest",
        ])
    else:
        cmd.extend([
            "-c:v", "libx264",
            "-preset", preset,
            "-pix_fmt", "yuv420p",
        ])

    cmd.append(str(output_path))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise EncoderError(
                f"ffmpeg failed (exit {result.returncode}):\n{result.stderr[-500:]}")
    except FileNotFoundError:
        raise EncoderError(f"ffmpeg not found at '{ffmpeg}'")


def _build_audio_filter(
    cmd: list[str],
    audio_inputs: list[tuple[Path, float, float, bool, float]],
    fps: int,
    total_frames: int,
) -> str:
    """Build ffmpeg audio filtergraph and append -i entries to cmd.

    Returns the filter_complex string.
    """
    total_duration = total_frames / fps
    streams: list[str] = []

    for idx, (audio_path, start_sec, duration_sec, loop, volume) in enumerate(audio_inputs):
        cmd.extend(["-i", str(audio_path)])
        stream_idx = idx + 1  # 0 is video input

        parts = []
        # Trim: delay silence until start_sec, then take audio
        if start_sec > 0:
            parts.append(f"adelay={int(start_sec * 1000)}|{int(start_sec * 1000)}")

        # Trim to duration if specified
        if duration_sec > 0:
            parts.append(f"atrim=0:{duration_sec}")

        # Volume
        if volume != 1.0:
            parts.append(f"volume={volume}")

        if parts:
            filter_chain = f"[{stream_idx}:a]{','.join(parts)}[a{idx}]"
        else:
            filter_chain = f"[{stream_idx}:a]anull[a{idx}]"

        streams.append(filter_chain)

    # Mix all audio streams
    mix_inputs = ''.join(f'[a{i}]' for i in range(len(audio_inputs)))
    streams.append(f"{mix_inputs}amix=inputs={len(audio_inputs)}:duration=longest[audio_out]")

    return ';'.join(streams)
