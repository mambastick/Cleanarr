"""ASGI entrypoint for CleanArr."""

from .api.app import create_app

app = create_app()
