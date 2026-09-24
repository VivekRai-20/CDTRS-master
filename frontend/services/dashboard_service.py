from typing import Any, Dict

from repositories.provider import get_repository


class DashboardService:
    """Dashboard counters for the active work context.

    Nothing is computed or filtered locally: the backend derives what this
    context is allowed to count from the X-Work-Context-Id header, so
    switching context changes the dashboard completely.
    """

    def get_summary(self) -> Dict[str, Any]:
        return get_repository().get_dashboard_summary()

    # Legacy name kept so existing callers keep working.
    def get_dashboard_summary(self, role: Any = None) -> Dict[str, Any]:
        return self.get_summary()


dashboard_service = DashboardService()
