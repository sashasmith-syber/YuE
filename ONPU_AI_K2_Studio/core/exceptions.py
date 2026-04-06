"""
Custom exception hierarchy for ONPU AI K2 Studio.
"""


class K2Error(Exception):
    """Base for all K2 exceptions."""

    def __init__(self, message: str, code: str = "K2_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class ConfigurationError(K2Error):
    """Invalid or missing configuration."""

    def __init__(self, message: str):
        super().__init__(message, code="CONFIG_ERROR")


class ValidationError(K2Error):
    """Request or input validation failed."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message, code="VALIDATION_ERROR")
        self.field = field


class EngineError(K2Error):
    """Generation engine failed."""

    def __init__(self, message: str, engine: str = ""):
        super().__init__(message, code="ENGINE_ERROR")
        self.engine = engine


class MusicGenError(EngineError):
    """MusicGen-specific failure."""

    def __init__(self, message: str):
        super().__init__(message, engine="musicgen")


class YuEError(EngineError):
    """YuE subprocess or inference failure."""

    def __init__(self, message: str):
        super().__init__(message, engine="yue")


class AnalysisError(K2Error):
    """Soundblueprint / DNA analysis failed."""

    def __init__(self, message: str):
        super().__init__(message, code="ANALYSIS_ERROR")


class RateLimitError(K2Error):
    """Rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, code="RATE_LIMIT")


class AuthError(K2Error):
    """Authentication or authorization failed."""

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, code="AUTH_ERROR")
