#!/usr/bin/env python3
"""Backward-compatible server entry point.

The application itself lives in :mod:`app.main`; this module keeps the
documented commands working:

    python server.py
    uvicorn server:app --reload
"""

from app.main import app, main

__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
