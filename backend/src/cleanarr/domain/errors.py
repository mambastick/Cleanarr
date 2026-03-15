"""Domain-level exceptions."""


class CleanArrError(Exception):
    """Base CleanArr exception."""


class ExternalServiceError(CleanArrError):
    """Raised when a downstream service cannot be used."""

    def __init__(self, system: str, message: str) -> None:
        super().__init__(message)
        self.system = system
        self.message = message


class ResourceNotFoundError(ExternalServiceError):
    """Raised when a downstream resource is absent."""


class AuthenticationError(ExternalServiceError):
    """Raised when a downstream service rejects credentials."""
