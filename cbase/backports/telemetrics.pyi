"""Logging utilities backported from PyAlgoEngine (Cython implementation)."""

import logging
import sys
from typing import Any

LOG_LEVEL: int


class ColoredFormatter(logging.Formatter):
    """Logging Formatter to add colors and count warning / errors.

    One ``logging.Formatter`` is pre-built per level bucket in ``__init__``;
    ``format()`` is a single cached lookup instead of rebuilding the
    ANSI-wrapped format string and a fresh formatter on every call.

    Attributes:
        format_str: Base (uncolored) format string.
        date_fmt: Date format used by the underlying formatters.
        style: Logging style ('%', '{' or '$') of the format string.
    """

    format_str: str
    date_fmt: str
    style: str

    def __init__(self, fmt: str | None = None, datefmt: str | None = None, style: str = '{', validate: bool = True) -> None:
        """Initialize the formatter and pre-build one formatter per level.

        Args:
            fmt: Base format string; defaults to the telemetrics template.
            datefmt: Date format for ``asctime``.
            style: Logging style of ``fmt`` ('%', '{' or '$').
            validate: Validate ``fmt`` against ``style``.
        """
        ...

    def _get_format(self, level: int, select: bool = False) -> str:
        """Return the ANSI-wrapped format string for a log level.

        Args:
            level: Log level number.
            select: Append the ';7' reverse-video modifier.
        """
        ...

    def format(self, record: logging.LogRecord) -> str:
        """Format a record with the pre-built formatter for its level."""
        ...


class DuplicateWarningFilter(logging.Filter):
    """Filter that lets each WARNING message pass only once per handler.

    Duplicate WARNING messages (identical formatted text) are dropped after
    the first occurrence; all other levels always pass.
    """

    def __init__(self, name: str = '') -> None:
        """Initialize the filter.

        Args:
            name: Filter name (see ``logging.Filter``).
        """
        ...

    def filter(self, record: logging.LogRecord) -> bool:
        """Return True when the record must be emitted, False when dropped."""
        ...


def get_logger(name: str, **kwargs: Any) -> logging.Logger:
    """Return the process-wide singleton logger for the given name.

    The first call with a given name creates and configures the logger
    (level, stream handler, formatter, duplicate-warning filter) and caches
    it; later calls with the same name return the same instance.

    Args:
        name: Logger name; each name gets its own singleton.
        level: Logging level threshold for the logger and its handler.
        stream_io: Output stream for the handler; falsy disables handlers.
        formatter: Formatter attached to the created stream handler.

    Returns:
        The cached ``logging.Logger`` instance for ``name``.
    """
    ...
