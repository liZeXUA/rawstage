class RawStageError(Exception):
    """Base exception for RawStage."""
    pass


class ParseError(RawStageError):
    """XML is malformed or contains invalid structure."""
    pass


class AssetError(RawStageError):
    """Referenced asset (image, audio) not found or failed to load."""
    pass


class RenderError(RawStageError):
    """Error during frame rendering or encoding."""
    pass
