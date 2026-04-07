"""Domain-specific exceptions."""


class AirPlatformError(Exception):
    """Base application error."""


class SchemaLoadError(AirPlatformError):
    """Raised when the JSON schema cannot be loaded."""


class ValidationError(AirPlatformError):
    """Raised when raw data fails hard validation rules."""


class DataNotFoundError(AirPlatformError):
    """Raised when a requested station or dataset cannot be found."""


class StorageError(AirPlatformError):
    """Raised when metrics storage fails."""
