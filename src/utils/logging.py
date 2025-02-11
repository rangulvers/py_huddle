from loguru import logger
import os

def setup_logging(debug_mode: bool):
    """
    Configure logging with comprehensive debug information.

    Args:
        debug_mode: Boolean to enable/disable debug logging
    """
    # Remove any existing handlers
    logger.remove()

    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)

    # Common format elements
    time_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green>"
    level_format = "<level>{level: <8}</level>"
    location_format = "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"
    process_format = "<blue>[{process.name}:{process.id}]</blue>"
    thread_format = "<blue>[{thread.name}]</blue>"

    # Debug format includes more details
    debug_format = (
        f"{time_format} | "
        f"{level_format} | "
        f"{process_format} {thread_format} | "
        f"{location_format} | "
        "<level>"
        "Message: {message} "
        "{exception}"
        "</level>"
    )

    # Regular format is more concise
    regular_format = (
        f"{time_format} | "
        f"{level_format} | "
        f"{location_format} | "
        "<level>{message}</level>"
    )

    # Set log level based on debug mode
    log_level = "DEBUG" if debug_mode else "INFO"

    # File handler with rotation and retention
    logger.add(
        "logs/app.log",
        rotation="500 MB",
        retention="10 days",
        level=log_level,
        format=debug_format if debug_mode else regular_format,
        backtrace=debug_mode,
        diagnose=debug_mode,
        enqueue=True,
        catch=True,
    )

    # Debug log file (only in debug mode)
    if debug_mode:
        logger.add(
            "logs/debug.log",
            rotation="100 MB",
            retention="3 days",
            level="DEBUG",
            format=debug_format,
            filter=lambda record: record["level"].name == "DEBUG",
            backtrace=True,
            diagnose=True,
            enqueue=True,
            catch=True,
        )

    # Console handler with custom sink to prevent extra newlines
    def console_sink(message):
        print(message, end="" if message.endswith("\n") else "\n")

    logger.add(
        console_sink,
        level=log_level,
        format=debug_format if debug_mode else regular_format,
        colorize=True,
        backtrace=debug_mode,
        diagnose=debug_mode,
    )

    # Log initial debug status
    logger.info(f"Logging initialized (Debug mode: {debug_mode})")
    if debug_mode:
        logger.debug("Debug logging enabled with extended information")
