from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class AttachmentInfo:
    part: str
    filename: str | None
    content_type: str
    size: int
    content_id: str | None = None
    inline: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MessageSummary:
    uid: str
    mailbox: str
    subject: str
    sender: str
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    date: datetime | None = None
    message_id: str | None = None
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    size: int | None = None
    flags: list[str] = field(default_factory=list)
    attachments: list[AttachmentInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["date"] = self.date.isoformat() if self.date else None
        return result


@dataclass(slots=True)
class MessageDetail:
    summary: MessageSummary
    text: str | None = None
    html: str | None = None
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary.to_dict(),
            "text": self.text,
            "html": self.html,
            "truncated": self.truncated,
        }


@dataclass(slots=True)
class Thread:
    root_message_id: str | None
    messages: list[MessageSummary]

    def to_dict(self) -> dict[str, Any]:
        return {
            "root_message_id": self.root_message_id,
            "messages": [message.to_dict() for message in self.messages],
        }


@dataclass(slots=True)
class AttachmentData:
    info: AttachmentInfo
    content: bytes

