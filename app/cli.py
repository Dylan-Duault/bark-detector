"""Maintenance commands: python -m app.cli --help."""
import argparse
import json
from pathlib import Path

from app.config import Settings
from app.infrastructure.database import Database, DATABASE
from app.services.migration import initialize, verify_legacy


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('web', 'detector', 'migrate', 'verify', 'sync', 'revision'):
        child = sub.add_parser(name)
        child.add_argument('--data-dir', type=Path)
        if name == 'web':
            child.add_argument('--host')
            child.add_argument('--port', type=int)
        if name == 'revision':
            child.add_argument('message')
    args = parser.parse_args(argv)
    overrides = {key: value for key, value in vars(args).items() if key in ('data_dir', 'host', 'port') and value is not None}
    settings = Settings(**overrides)
    if args.command == 'web':
        import uvicorn
        from app.main import create_app
        uvicorn.run(create_app(settings), host=settings.host, port=settings.port, proxy_headers=False)
        return
    if args.command == 'detector':
        from app.detector import main as detector_main
        detector_main(settings)
        return
    database = Database(settings.data_dir)
    try:
        if args.command == 'verify':
            if not (settings.data_dir / DATABASE).is_file():
                parser.error('Database missing. Run migrate first.')
            report = verify_legacy(database)
        else:
            report = initialize(database)
            if args.command == 'revision':
                from alembic import command
                from alembic.config import Config
                config = Config()
                config.set_main_option('script_location', str(Path(__file__).parent / 'migrations'))
                with database.maintenance(), database.engine.begin() as connection:
                    config.attributes['connection'] = connection
                    command.revision(config, message=args.message, autogenerate=True)
            report['verification'] = verify_legacy(database)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        valid = report.get('ok', report.get('verification', {}).get('ok', True))
        if not valid:
            raise SystemExit(1)
    finally:
        database.close()


if __name__ == '__main__':
    main()
