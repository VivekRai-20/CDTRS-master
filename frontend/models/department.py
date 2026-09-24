from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class DepartmentModel:
    """
    Frontend domain model representing an institutional Department.
    """
    id: int
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True

    def get(self, key: str, default: Any = None) -> Any:
        if hasattr(self, key):
            val = getattr(self, key)
            return val if val is not None else default
        return default

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DepartmentModel":
        return cls(
            id=data.get("id") or data.get("department_id") or 0,
            name=data.get("name") or data.get("department_name") or "General",
            code=data.get("code"),
            description=data.get("description"),
            is_active=bool(data.get("is_active", True))
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "description": self.description,
            "is_active": self.is_active
        }
