"""Convenience entry point for the CV Search API server."""

import uvicorn

from cv_search.api.main import app
from cv_search.config.settings import Settings


def main():
    settings = Settings()
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
    )


if __name__ == "__main__":
    main()
