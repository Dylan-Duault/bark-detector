import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from app.dependencies import dashboard_service
from app.schemas import DashboardResponse
from app.services.dashboard import Dashboard

router = APIRouter(prefix='/api', tags=['Dashboard'])


@router.api_route('/dashboard', methods=['GET', 'HEAD'], response_model=DashboardResponse)
def dashboard(service: Annotated[Dashboard, Depends(dashboard_service)],
              date: Annotated[str | None, Query(pattern=r'^\d{4}-\d{2}-\d{2}$')] = None,
              period: int = 7):
    try:
        if date:
            dt.date.fromisoformat(date)
        return service.snapshot(date, period)
    except ValueError as error:
        raise HTTPException(400, 'Date invalide ou période différente de 7 / 30 jours.') from error
