import uvicorn

from treesleuth.config import get_settings
from treesleuth.logging_config import configure_logging


def main() -> None:
    configure_logging()
    settings = get_settings()
    uvicorn.run("treesleuth.main:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
