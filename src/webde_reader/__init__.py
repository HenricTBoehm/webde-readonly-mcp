"""Read-only WEB.DE IMAP access."""

from .client import ReadOnlyImapClient
from .config import AccountConfig

__all__ = ["AccountConfig", "ReadOnlyImapClient"]
__version__ = "0.1.0"

