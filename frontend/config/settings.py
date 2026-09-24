import os
from dataclasses import dataclass


def _load_env_file():
    """Attempts to load .env file from current, frontend, or root directory."""
    search_paths = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"),
    ]
    for env_path in search_paths:
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, val = line.split("=", 1)
                            key = key.strip()
                            val = val.strip().strip('"').strip("'")
                            if key and key not in os.environ:
                                os.environ[key] = val
                break
            except Exception:
                pass


_load_env_file()


@dataclass
class Settings:
    """
    Centralized configuration for CDTRS Frontend.
    Reads environment variables with sensible defaults.
    """

    # 1. API Base URL (defaults to local backend http://127.0.0.1:8000/api/v1 or LAN / Cloud URL)
    api_url: str = os.getenv("CDTRS_API_URL", os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api/v1")).rstrip("/")
    
    # The frontend uses the live FastAPI backend.
    # Kept as a property rather than a mutable mode switch so there is only
    # one supported runtime data source.
    data_source: str = "api"

    # Network Request Timeout in seconds
    api_timeout: float = float(os.getenv("CDTRS_API_TIMEOUT", "15.0"))

    # Application Information
    app_name: str = os.getenv("CDTRS_APP_NAME", "CDTRS")
    app_version: str = os.getenv("CDTRS_APP_VERSION", "2.0.0")

    @property
    def is_api_mode(self) -> bool:
        """Returns True if the application is configured to connect to live backend API."""
        return self.data_source == "api"

    @property
    def api_base_url(self) -> str:
        """Returns the root host URL without /api/v1 suffix."""
        if self.api_url.endswith("/api/v1"):
            return self.api_url[:-7]
        return self.api_url


    def set_api_url(self, url: str) -> None:
        """Dynamically update the API Base URL at runtime."""
        self.api_url = url.strip().rstrip("/")

    def set_data_source(self, mode: str) -> None:
        """Retained for compatibility; CDTRS only supports API mode."""
        if mode.strip().lower() != "api":
            raise ValueError("CDTRS frontend supports only API data source mode.")
        self.data_source = "api"


# Global singleton settings instance
settings = Settings()