"""Write domain events once, separately from diagnostic logs."""
from sqlalchemy.dialects.sqlite import insert
from app.models import BarkSession, Day, Detection, MusicEvent


class History:
    def __init__(self, database):
        self.database = database

    def _write(self, model, values):
        with self.database.session.begin() as session:
            session.execute(insert(Day).values(date=values['date'], has_log=True)
                            .on_conflict_do_update(index_elements=['date'], set_={'has_log': True}))
            session.add(model(**values))

    def detection(self, timestamp, volume):
        self._write(Detection, dict(date=timestamp.date().isoformat(), hour=timestamp.hour,
                                   occurred_at=timestamp.isoformat(), volume=float(volume)))

    def bark_session(self, start, end, seconds, count):
        self._write(BarkSession, dict(date=end.date().isoformat(), started_at=start.isoformat(),
                                     ended_at=end.isoformat(), seconds=seconds, count=count))

    def music(self, timestamp, status, track, detail=''):
        self._write(MusicEvent, dict(date=timestamp.date().isoformat(), time=timestamp.strftime('%H:%M:%S'),
                                    status=status, track=track, detail=detail))
