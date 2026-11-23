import logging
from logging.handlers import RotatingFileHandler
from config import LOG_FILE


def setup_logger(name="AI_Intelligence_Pipeline"):

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console logging
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # File logging with rotation
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8"
    )

    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


logger = setup_logger()


if __name__ == "__main__":

    logger.info("AI Intelligence Data Pipeline started.")
    logger.warning("This is a sample warning message.")
    logger.error("This is a sample error message.")

    print("\nLogger is working successfully!")
    print("Log file:", LOG_FILE)