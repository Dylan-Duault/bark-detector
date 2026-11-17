"""Dashboard read model: SQL aggregates, no log parsing or audio scanning."""
import datetime as dt

from sqlalchemy import func, select
from app.models import BarkSession, Day, Detection, MusicEvent, Recording
from app.services.monitoring import monitoring_snapshot


def empty_day(date):
    return dict(date=date, detections=0, sessions=0, seconds=0, recordings=0,
                hours=[0]*24, listened_hours=None, listened_seconds=None, has_data=False)


class Dashboard:
    def __init__(self, database):
        self.database = database

    def snapshot(self, selected=None, period=7):
        if period not in (7, 30):
            raise ValueError('Period must be 7 or 30 days')
        date = selected or dt.date.today().isoformat()
        end = dt.date.fromisoformat(date)
        days = {}
        def day(key):
            return days.setdefault(key, empty_day(key))
        with self.database.session() as session:
            detector, coverage = monitoring_snapshot(session)
            logged_dates = set(session.scalars(select(Day.date).where(Day.has_log.is_(True))))
            for key in logged_dates:
                day(key)
            for key, hour, count in session.execute(select(Detection.date, Detection.hour, func.count()).group_by(Detection.date, Detection.hour)):
                day(key)['detections'] += count
                day(key)['hours'][hour] = count
            for key, count, seconds in session.execute(select(BarkSession.date, func.count(), func.sum(BarkSession.seconds)).group_by(BarkSession.date)):
                day(key).update(sessions=count, seconds=seconds)
            for key, count in session.execute(select(Recording.date, func.count()).group_by(Recording.date)):
                day(key)['recordings'] = count
            for key, hours in coverage.items():
                day(key).update(listened_hours=hours, listened_seconds=sum(hours))
            for key, item in days.items():
                item['has_data'] = key in logged_dates or bool(item['listened_seconds'])
            music = [dict(date=e.date, time=e.time, status=e.status, track=e.track, detail=e.detail)
                     for e in session.scalars(select(MusicEvent).where(MusicEvent.date == date).order_by(MusicEvent.id.desc()))]
            recordings = [dict(name=r.name, date=r.date, time=r.time, duration=r.duration, url='/audio/' + r.name)
                          for r in session.scalars(select(Recording).where(Recording.date == date).order_by(Recording.name.desc()))]
        trend_days = []
        for offset in range(period-1, -1, -1):
            key = (end - dt.timedelta(days=offset)).isoformat()
            trend_days.append(dict(days.get(key, empty_day(key)), has_log=key in logged_dates))
        trends = dict(period=period, start=trend_days[0]['date'], end=date, days=trend_days,
                      hours=[sum(item['hours'][h] for item in trend_days) for h in range(24)],
                      listened_seconds=sum(item['listened_seconds'] or 0 for item in trend_days)
                      if any(item['listened_seconds'] is not None for item in trend_days) else None)
        return dict(date=date, detector=detector, music_events=music, summary=days.get(date, empty_day(date)),
                    days=sorted(days.values(), key=lambda d: d['date'], reverse=True), trends=trends, recordings=recordings)


def dashboard_data(directory, selected=None, period=7):
    """Offline convenience for migration checks/tests. HTTP uses Dashboard directly."""
    from app.infrastructure.database import Database
    from app.services.migration import initialize
    database = Database(directory)
    try:
        initialize(database)
        return Dashboard(database).snapshot(selected, period)
    finally:
        database.close()
