import wave
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.schemas import WaveformResponse
from app.services.recordings import recording_levels, recording_path

router = APIRouter(tags=['Recordings'])


def resolve(request, name):
    try:
        return recording_path(request.app.state.settings.data_dir, name)
    except FileNotFoundError as error:
        raise HTTPException(404, 'Enregistrement introuvable.') from error


@router.api_route('/audio/{name}', methods=['GET', 'HEAD'])
def audio(request: Request, name: str):
    return FileResponse(resolve(request, name), media_type='audio/wav')


@router.api_route('/api/waveform/{name}', methods=['GET', 'HEAD'], response_model=WaveformResponse)
def waveform(request: Request, name: str):
    path = resolve(request, name)
    try:
        stat = path.stat()
        return recording_levels(path, stat.st_mtime_ns, stat.st_size)
    except (OSError, EOFError, wave.Error, ValueError) as error:
        raise HTTPException(404, 'Analyse audio indisponible.') from error
