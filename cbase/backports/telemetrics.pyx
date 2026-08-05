import logging
import sys
import time

# logging.WARNING — stable across CPython releases; a C-level constant so the
# filter hot path never re-reads the logging module.
cdef int _WARNING_LEVEL = 30

# Singleton for the default logger name ('PyAlgoEngine'); None until the
# first get_logger() call, exactly like the upstream module.
LOGGER = None
LOG_LEVEL = logging.INFO

# Per-name logger singletons: name -> logging.Logger
cdef dict _loggers = {}

# ANSI escape codes — module-level constants, built once at import time
# instead of on every _get_format() call. The color codes omit the trailing
# 'm' so the ';7' reverse-video suffix can be appended when select=True.
cdef str _ANSI_RESET = "\33[0m"
cdef str _ANSI_BOLD_RED = "\33[31;1;3;4"
cdef str _ANSI_RED = "\33[31;1"
cdef str _ANSI_GREEN = "\33[32;1"
cdef str _ANSI_YELLOW = "\33[33;1"
cdef str _ANSI_BLUE = "\33[34;1"
cdef str _ANSI_SELECT = ";7"

cdef int _level_index(int level):
    """Map a log level to the index of the pre-built formatter tuple.

    Mirrors the upstream `_get_format` level buckets: <=NOTSET plain,
    <=DEBUG blue, <=INFO green, <=WARNING yellow, <=ERROR red, else bold red.
    """
    if level <= 0:
        return 0
    if level <= 10:
        return 1
    if level <= 20:
        return 2
    if level <= 30:
        return 3
    if level <= 40:
        return 4
    return 5


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

    def __init__(self, fmt=None, datefmt=None, style='{', validate=True):
        self.format_str = '[{asctime} {name} - {threadName} - {module}:{lineno} - {levelname}] {message}' if fmt is None else fmt
        self.date_fmt = '%Y-%m-%d %H:%M:%S' if datefmt is None else datefmt
        self.style = style

        super().__init__(fmt=fmt, datefmt=datefmt, style=style, validate=validate)

        # One formatter per level bucket, indexed by `_level_index`.
        self._formatters = tuple(
            logging.Formatter(self._get_format(level), datefmt=self.date_fmt, style=self.style)
            for level in (logging.NOTSET, logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL)
        )

    def _get_format(self, level: int, select=False):
        suffix = _ANSI_SELECT if select else ""
        bold_red = _ANSI_BOLD_RED + suffix + "m"
        red = _ANSI_RED + suffix + "m"
        green = _ANSI_GREEN + suffix + "m"
        yellow = _ANSI_YELLOW + suffix + "m"
        blue = _ANSI_BLUE + suffix + "m"
        reset = _ANSI_RESET

        if level <= logging.NOTSET:
            fmt = self.format_str
        elif level <= logging.DEBUG:
            fmt = blue + self.format_str + reset
        elif level <= logging.INFO:
            fmt = green + self.format_str + reset
        elif level <= logging.WARNING:
            fmt = yellow + self.format_str + reset
        elif level <= logging.ERROR:
            fmt = red + self.format_str + reset
        else:
            fmt = bold_red + self.format_str + reset

        return fmt

    def format(self, record):
        return self._formatters[_level_index(record.levelno)].format(record)


class DuplicateWarningFilter(logging.Filter):
    """Filter that lets each WARNING message pass only once per handler.

    Duplicate WARNING messages (identical formatted text) are dropped after
    the first occurrence; all other levels always pass.
    """

    def __init__(self, name: str = ''):
        super().__init__(name=name)
        self._seen_warnings: set[str] = set()

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno != _WARNING_LEVEL:
            return True

        # Fast path: without args getMessage() is just str(msg) — skip the
        # method dispatch. With args the full formatting is unavoidable.
        args = record.args
        message = str(record.msg) if not args else record.getMessage()
        if message in self._seen_warnings:
            return False

        self._seen_warnings.add(message)
        return True


def get_logger(**kwargs) -> logging.Logger:
    """Return the process-wide singleton logger for the given name.

    The first call with a given name creates and configures the logger
    (level, stream handler, formatter, duplicate-warning filter) and caches
    it; later calls with the same name return the same instance.

    Args:
        name: Logger name; each name gets its own singleton (default
            'PyAlgoEngine', matching the upstream default).
        level: Logging level threshold for the logger and its handler.
        stream_io: Output stream for the handler; falsy disables handlers.
        formatter: Formatter attached to the created stream handler.

    Returns:
        The cached ``logging.Logger`` instance for ``name``.
    """
    name = kwargs.get('name', 'PyAlgoEngine')
    global LOGGER

    if name in _loggers:
        return _loggers[name]

    level = kwargs.get('level', LOG_LEVEL)
    stream_io = kwargs.get('stream_io', sys.stdout)
    formatter = kwargs.get('formatter', ColoredFormatter())

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logging.Formatter.converter = time.gmtime

    if stream_io:
        have_handler = False
        stream_handler: logging.StreamHandler | None = None
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and handler.stream == stream_io:
                have_handler = True
                stream_handler = handler
                break

        if not have_handler:
            logger_ch = logging.StreamHandler(stream=stream_io)
            logger_ch.setLevel(level=level)
            logger_ch.setFormatter(fmt=formatter)
            logger.addHandler(logger_ch)
            stream_handler = logger_ch

        if stream_handler is not None and not any(isinstance(flt, DuplicateWarningFilter) for flt in stream_handler.filters):
            stream_handler.addFilter(DuplicateWarningFilter())

    _loggers[name] = logger
    if name == 'PyAlgoEngine':
        LOGGER = logger
    return logger
