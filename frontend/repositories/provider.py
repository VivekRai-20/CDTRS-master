from typing import Optional
from repositories.base import BaseRepository
from repositories.api_repository import APIRepository

_api_repo_instance: Optional[APIRepository] = None


def get_repository() -> BaseRepository:
    """
    Central repository provider for the CDTRS client.
    Always returns the real APIRepository. Offline/mock repository support is intentionally removed.
    Services and UI never manually check 'if data_source == mock'.
    """
    global _api_repo_instance

    if _api_repo_instance is None:
        _api_repo_instance = APIRepository()
    return _api_repo_instance

