import logging
import os
from logging.handlers import TimedRotatingFileHandler


def setup_logger(name="stackvm", log_level=logging.INFO):
    """
    Setup and configure logger

    Args:
        name (str): Name of the logger
        log_level (int): Logging level (e.g., logging.INFO, logging.DEBUG)

    Returns:
        logging.Logger: Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Return existing logger if handlers are already configured
    if logger.handlers:
        return logger

    # Create log directory if it doesn't exist
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Set log file path
    log_file = os.path.join(log_dir, f"{name}.log")

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    )

    # Create and configure file handler (daily rotation)
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=30,  # Keep logs for 30 days
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)

    # Create and configure console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)

    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# Create default logger instance
logger = setup_logger()
