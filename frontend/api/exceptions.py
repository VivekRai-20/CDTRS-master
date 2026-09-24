from typing import Any, Optional


class APIException(Exception):
    """Base exception for all CDTRS API errors."""

    def __init__(
        self,
        message: str = "An API error occurred.",
        status_code: Optional[int] = None,
        error_data: Optional[Any] = None
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_data = error_data

    def __str__(self) -> str:
        if self.status_code:
            return f"[{self.status_code}] {self.message}"
        return self.message


class NetworkError(APIException):
    """Raised when network connection fails, server is unreachable, or DNS fails."""

    def __init__(self, message: str = "Unable to connect to the CDTRS server. Please check your network.", error_data: Optional[Any] = None):
        super().__init__(message, status_code=None, error_data=error_data)


class TimeoutError(APIException):
    """Raised when a request exceeds configured timeout duration."""

    def __init__(self, message: str = "Request timed out while contacting the server.", error_data: Optional[Any] = None):
        super().__init__(message, status_code=408, error_data=error_data)


class UnauthorizedError(APIException):
    """Raised on HTTP 401 Unauthorized (invalid or expired authentication)."""

    def __init__(self, message: str = "Session expired or invalid credentials. Please log in again.", error_data: Optional[Any] = None):
        super().__init__(message, status_code=401, error_data=error_data)


class ForbiddenError(APIException):
    """Raised on HTTP 403 Forbidden (authenticated user lacks permission)."""

    def __init__(self, message: str = "You do not have permission to perform this action.", error_data: Optional[Any] = None):
        super().__init__(message, status_code=403, error_data=error_data)


class NotFoundError(APIException):
    """Raised on HTTP 404 Not Found."""

    def __init__(self, message: str = "Requested resource was not found.", error_data: Optional[Any] = None):
        super().__init__(message, status_code=404, error_data=error_data)


class ConflictError(APIException):
    """Raised on HTTP 409 Conflict (e.g., workflow state mismatch or concurrent edit)."""

    def __init__(self, message: str = "Workflow state conflict. The document state may have changed.", error_data: Optional[Any] = None):
        super().__init__(message, status_code=409, error_data=error_data)


class ValidationError(APIException):
    """Raised on HTTP 422 Unprocessable Entity (input data validation failure)."""

    def __init__(self, message: str = "Input data validation error.", error_data: Optional[Any] = None):
        super().__init__(message, status_code=422, error_data=error_data)


class ServerError(APIException):
    """Raised on HTTP 500+ Internal Server Errors."""

    def __init__(self, message: str = "Internal server error occurred on the backend.", status_code: int = 500, error_data: Optional[Any] = None):
        super().__init__(message, status_code=status_code, error_data=error_data)


def raise_for_status_code(status_code: int, detail_message: Optional[str] = None, error_data: Optional[Any] = None) -> None:
    """
    Translates HTTP status code into appropriate typed APIException.
    """
    if 200 <= status_code < 300:
        return

    msg = detail_message or "API request failed."

    if status_code == 401:
        raise UnauthorizedError(msg, error_data=error_data)
    elif status_code == 403:
        raise ForbiddenError(msg, error_data=error_data)
    elif status_code == 404:
        raise NotFoundError(msg, error_data=error_data)
    elif status_code == 408:
        raise TimeoutError(msg, error_data=error_data)
    elif status_code == 409:
        raise ConflictError(msg, error_data=error_data)
    elif status_code == 422:
        raise ValidationError(msg, error_data=error_data)
    elif status_code >= 500:
        raise ServerError(msg, status_code=status_code, error_data=error_data)
    else:
        raise APIException(msg, status_code=status_code, error_data=error_data)
