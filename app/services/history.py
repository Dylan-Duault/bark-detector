"""Write domain events once, separately from diagnostic logs."""
from datetime import timedelta

from sqlalchemy import literal, select, tuple_
from sqlalchemy.dialects.sqlite import insert
from app.models import BarkSession, Day, Detection, LiveVoiceEvent, MusicEvent


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

    def live_voice(self, timestamp):
        cutoff = timestamp - timedelta(minutes=2)
        recent = select(LiveVoiceEvent.id).where(
            tuple_(LiveVoiceEvent.date, LiveVoiceEvent.time)
            > (cutoff.date().isoformat(), cutoff.strftime('%H:%M:%S'))
        ).exists()
        event = select(literal(timestamp.date().isoformat()), literal(timestamp.strftime('%H:%M:%S')))
        # Keep the check and insert in a single statement for concurrent presses.
        statement = insert(LiveVoiceEvent).from_select(['date', 'time'], event.where(~recent))
        with self.database.session.begin() as session:
            session.execute(statement)
