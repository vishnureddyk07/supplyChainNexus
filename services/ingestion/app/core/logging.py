import logging


def configure_logging(log_level: str = "INFO") -> None:
	logging.basicConfig(
		level=getattr(logging, log_level.upper(), logging.INFO),
		format="%(asctime)s %(levelname)s %(name)s %(message)s",
	)
	logging.getLogger("uvicorn.error").setLevel(logging.INFO)
	logging.getLogger("uvicorn.access").setLevel(logging.INFO)
