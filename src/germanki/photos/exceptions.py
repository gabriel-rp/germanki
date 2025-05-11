from germanki.utils import get_logger

logger = get_logger(__file__)


class PhotosAPIError(Exception):
    """Base exception for Pexels API errors."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logger.debug(str(self))


class PhotosRateLimitError(PhotosAPIError):
    """Raised when the API rate limit is exceeded."""

    pass


class PhotosAuthenticationError(PhotosAPIError):
    """Raised when API authentication fails."""

    pass


class PhotosNotFoundError(PhotosAPIError):
    """Raised when a requested resource is not found."""

    pass


class PhotosNoResultsError(PhotosAPIError):
    """Raised when no results are found for a search query."""

    pass
