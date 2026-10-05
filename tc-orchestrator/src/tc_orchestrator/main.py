"""Uvicorn entrypoint for the TC Orchestrator."""

from __future__ import annotations

from .api import create_app
from .config import load_settings


def main() -> None:
    settings = load_settings()
    application = create_app(settings=settings)
    import uvicorn

    uvicorn.run(application, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
