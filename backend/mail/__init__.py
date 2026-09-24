import warnings

# requests 2.32.3 warns about the installed chardet 7.x / urllib3 2.7 at import
# time.  Both work with it; the versions are fixed by the deployment, so the
# warning is silenced before anything imports requests.
warnings.filterwarnings(
    "ignore", message=r"urllib3 \(.*\) or chardet \(.*\)/charset_normalizer \(.*\) doesn't match a supported version"
)
from .base import BaseMailProvider, IncomingEmailDTO, OutgoingEmailDTO, EmailAttachmentDTO
from .outlook_provider import OutlookGraphProvider
from .service import mail_service

__all__ = [
    "BaseMailProvider",
    "IncomingEmailDTO",
    "OutgoingEmailDTO",
    "EmailAttachmentDTO",
    "OutlookGraphProvider",
    "mail_service",
]
