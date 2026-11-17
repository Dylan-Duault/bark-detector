"""Small, explicit injection points for controllers and tests."""
from fastapi import Request


def dashboard_service(request: Request):
    return request.app.state.dashboard


def database(request: Request):
    return request.app.state.database
