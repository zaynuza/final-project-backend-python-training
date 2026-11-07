"""Infrastructure: catatan notifikasi yang sudah terkirim, untuk idempotency.

key = event_id. Kolom key unique, jadi satu event hanya tercatat sekali walaupun pesannya datang berkali-kali.
"""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.infrastructure.models import SentNotificationRecord


class SqlAlchemyNotificationLog:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def already_sent(self, key: str) -> bool:
        with self.session_factory() as session:
            return session.get(SentNotificationRecord, key) is not None

    def mark_sent(self, key: str) -> None:
        try:
            with self.session_factory.begin() as session:
                session.add(SentNotificationRecord(key=key))
        except IntegrityError:
            pass                      # worker lain sudah mencatatnya duluan
