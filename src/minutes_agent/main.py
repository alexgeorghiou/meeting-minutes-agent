"""ASGI entry point: ``uvicorn minutes_agent.main:app``."""

from __future__ import annotations

import logging

from minutes_agent.api import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = create_app()
