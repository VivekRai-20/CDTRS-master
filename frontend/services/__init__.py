from services.auth_service import AuthService, auth_service, authenticate
from services.document_service import DocumentService, document_service
from services.routing_service import RoutingService, routing_service
from services.work_service import WorkService, work_service
from services.attachment_service import AttachmentService, attachment_service
from services.notification_service import NotificationService, notification_service
from services.dashboard_service import DashboardService, dashboard_service
from services.ocr_service import OCRService, ocr_service
from services.admin_service import AdminService, admin_service

__all__ = [
    "AuthService", "auth_service", "authenticate",
    "DocumentService", "document_service",
    "RoutingService", "routing_service",
    "WorkService", "work_service",
    "AttachmentService", "attachment_service",
    "NotificationService", "notification_service",
    "DashboardService", "dashboard_service",
    "OCRService", "ocr_service",
    "AdminService", "admin_service",
]
