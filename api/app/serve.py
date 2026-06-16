import uvicorn

from app.config import get_host, get_log_level, get_port


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=get_host(),
        port=get_port(),
        log_level=get_log_level().lower(),
    )


if __name__ == "__main__":
    main()
