from __future__ import annotations

import os
from dataclasses import dataclass

HOST = "imap.web.de"
PORT = 993
KEYRING_SERVICE = "webde-reader-imap"


class ConfigurationError(RuntimeError):
    """Raised when local account configuration is incomplete."""


def _keyring_module():
    try:
        import keyring  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ConfigurationError(
            "OS keyring support is not installed. Install with "
            "'pip install -e .[secrets]' or set WEBDE_IMAP_PASSWORD."
        ) from exc
    return keyring


def save_password(username: str, password: str) -> None:
    if not username or not password:
        raise ConfigurationError("Username and app password must not be empty.")
    _keyring_module().set_password(KEYRING_SERVICE, username, password)


def delete_password(username: str) -> None:
    keyring = _keyring_module()
    try:
        keyring.delete_password(KEYRING_SERVICE, username)
    except keyring.errors.PasswordDeleteError as exc:
        raise ConfigurationError("No stored password was found for this account.") from exc


def load_password(username: str) -> str:
    env_password = os.environ.get("WEBDE_IMAP_PASSWORD")
    if env_password:
        return env_password
    password = _keyring_module().get_password(KEYRING_SERVICE, username)
    if not password:
        raise ConfigurationError(
            "No app password found. Run 'webde-reader credentials set <address>' "
            "or set WEBDE_IMAP_PASSWORD for this process."
        )
    return password


@dataclass(frozen=True, slots=True)
class AccountConfig:
    username: str
    password: str
    timeout: float = 30.0
    host: str = HOST
    port: int = PORT

    def __post_init__(self) -> None:
        if self.host != HOST or self.port != PORT:
            raise ConfigurationError(
                f"This client is locked to the WEB.DE endpoint {HOST}:{PORT}."
            )
        if not self.username.strip():
            raise ConfigurationError("The WEB.DE username must not be empty.")
        if not self.password:
            raise ConfigurationError("The WEB.DE app password must not be empty.")

    @classmethod
    def from_environment(cls) -> AccountConfig:
        username = os.environ.get("WEBDE_IMAP_USER", "").strip()
        if not username:
            raise ConfigurationError("Set WEBDE_IMAP_USER to your complete WEB.DE address.")
        return cls(username=username, password=load_password(username))

