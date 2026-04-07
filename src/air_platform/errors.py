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


class LLMError(AirPlatformError):
    """Base error for LLM provider failures."""


class LLMProviderError(LLMError):
    """Raised for provider-side errors (bad status, rate limit, etc.)."""


class LLMTimeoutError(LLMError):
    """Raised when an LLM call exceeds its timeout budget."""


class LLMNotConfiguredError(LLMError):
    """Raised when required LLM credentials are absent."""


class LLMStructuredOutputError(LLMError):
    """Raised when structured output from the LLM fails validation."""
