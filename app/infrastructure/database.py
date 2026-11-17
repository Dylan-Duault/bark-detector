"""SQLite connections and explicit Alembic schema upgrades."""
from contextlib import contextmanager
import fcntl
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import sessionmaker

DATABASE = 'bark.sqlite3'


class Database:
    def __init__(self, directory: Path):
        self.directory = Path(directory).resolve()
        self.engine = create_engine(
            URL.create('sqlite', database=str(self.directory / DATABASE)),
            connect_args={'check_same_thread': False, 'timeout': 10})
        event.listen(self.engine, 'connect', self._configure)
        self.session = sessionmaker(self.engine, expire_on_commit=False)

    @staticmethod
    def _configure(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=10000')

    @contextmanager
    def maintenance(self):
        """Serialize schema upgrades/imports between web, detector and CLI."""
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / '.migration.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def upgrade(self):
        config = Config()
        config.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'migrations'))
        with self.engine.begin() as connection:
            config.attributes['connection'] = connection
            command.upgrade(config, 'head')
        with self.engine.connect() as connection:
            connection.exec_driver_sql('PRAGMA journal_mode=WAL')

    def close(self):
        self.engine.dispose()
