import subprocess
from typing import Literal
from fastapi import APIRouter, HTTPException
from app.infrastructure.journal import live_logs

router = APIRouter(prefix='/api', tags=['System logs'])


@router.get('/logs')
def logs(source: Literal['detector', 'dashboard'] = 'detector'):
    try:
        return live_logs(source)
    except (OSError, subprocess.SubprocessError) as error:
        raise HTTPException(503, 'Lecture du journal indisponible.') from error
