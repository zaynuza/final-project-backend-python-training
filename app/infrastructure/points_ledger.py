"""Infrastructure: buku poin customer di database, adapter untuk port PointsLedger.

add() mencatat event_id dan menambah poin dalam satu transaksi.
event_id adalah primary key di tabel point_events, jadi event yang sama tidak bisa tercatat dua kali.

Dua consumer bisa memproses event customer yang sama bersamaan, jadi:
- Event dicatat dengan INSERT ... ON CONFLICT DO NOTHING ... RETURNING. Tidak ada baris kembali = sudah pernah diproses.
  (rowcount tidak dipakai: untuk INSERT lewat ORM di PostgreSQL nilainya -1.)
  Tidak ada try/except IntegrityError, supaya error lain (misalnya tabel saldo) tidak salah dianggap "sudah diproses".
- Baris saldo customer baru dibuat dengan cara yang sama (poin 0), jadi dua event pertama bersamaan tidak saling gagal.
- Poin ditambah di database: UPDATE ... SET points = points + :n. Bukan dibaca ke Python lalu ditulis lagi,
  yang bisa menimpa tambahan consumer lain (lost update).
"""
from sqlalchemy import update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.models import CustomerPointsRecord, PointEventRecord


def insert_ignore(session: Session, model, **values):
    """INSERT ... ON CONFLICT DO NOTHING. PostgreSQL untuk production, SQLite untuk test."""
    insert = postgresql.insert if session.get_bind().dialect.name == "postgresql" else sqlite.insert
    return insert(model).values(**values).on_conflict_do_nothing()


class SqlAlchemyPointsLedger:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def add(self, event_id: str, customer: str, points: int) -> bool:
        with self.session_factory.begin() as session:
            recorded = session.execute(
                insert_ignore(session, PointEventRecord, event_id=event_id, customer=customer, points=points)
                .returning(PointEventRecord.event_id)).first()
            if recorded is None:
                return False                              # tidak ada baris baru = event sudah pernah diproses
            session.execute(insert_ignore(session, CustomerPointsRecord, customer=customer, points=0))
            session.execute(update(CustomerPointsRecord)
                            .where(CustomerPointsRecord.customer == customer)
                            .values(points=CustomerPointsRecord.points + points))
        return True

    def balance(self, customer: str) -> int:
        with self.session_factory() as session:
            record = session.get(CustomerPointsRecord, customer)
            return record.points if record else 0
