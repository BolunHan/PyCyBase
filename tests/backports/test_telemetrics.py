"""Test suite for cbase.backports.telemetrics.

Contract: get_logger returns a per-name process-wide singleton logger
configured with level, stream, formatter and a duplicate-warning filter;
ColoredFormatter wraps the base format string in per-level ANSI colors;
DuplicateWarningFilter passes each WARNING message once and drops repeats.

Oracle: expected ANSI codes and format substrings derived independently from
the documented color scheme; singleton semantics verified by object identity.
"""
import io
import logging
import time
import unittest

from cbase.backports import ColoredFormatter, DuplicateWarningFilter, LOG_LEVEL, get_logger
from cbase.backports import telemetrics as tm


def _make_record(levelno: int, msg: str, args: tuple = (), name: str = 'test.telemetrics') -> logging.LogRecord:
    """Build a LogRecord without emitting it anywhere."""
    return logging.LogRecord(name, levelno, __file__, 1, msg, args, None)


# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------

class TestGetLogger(unittest.TestCase):
    """Contract: get_logger() is a singleton per name and configures the
    logger once (level, stream handler, formatter, warning filter).

    Expected behavior:
        - repeated calls with the same name return the same logger;
        - different names yield independent loggers;
        - kwargs only affect the first call for a given name.
    """

    def test_00_default_singleton(self) -> None:
        """Repeated no-arg calls return the same 'PyAlgoEngine' logger."""
        logger_a = get_logger()
        logger_b = get_logger()
        self.assertIs(logger_a, logger_b)
        self.assertEqual(logger_a.name, 'PyAlgoEngine')

    def test_01_per_name_singleton(self) -> None:
        """Repeated calls with the same name return the same logger."""
        logger_a = get_logger(name='tm_per_name_singleton')
        logger_b = get_logger(name='tm_per_name_singleton')
        self.assertIs(logger_a, logger_b)

    def test_02_name_isolation(self) -> None:
        """Different names yield different logger objects."""
        logger_a = get_logger(name='tm_name_isolation_a')
        logger_b = get_logger(name='tm_name_isolation_b')
        self.assertIsNot(logger_a, logger_b)

    def test_03_level_kwarg(self) -> None:
        """level kwarg applies to the logger and its stream handler."""
        logger = get_logger(name='tm_level_kwarg', level=logging.DEBUG)
        self.assertEqual(logger.level, logging.DEBUG)
        handler = logger.handlers[0]
        self.assertEqual(handler.level, logging.DEBUG)

    def test_04_stream_io_kwarg(self) -> None:
        """stream_io kwarg binds the handler to the given stream exactly once."""
        stream = io.StringIO()
        logger = get_logger(name='tm_stream_io_kwarg', stream_io=stream)
        matching = [h for h in logger.handlers if h.stream is stream]
        self.assertEqual(len(matching), 1)

    def test_05_formatter_kwarg(self) -> None:
        """formatter kwarg attaches the given formatter to the handler."""
        formatter = logging.Formatter('%(levelname)s')
        logger = get_logger(name='tm_formatter_kwarg', formatter=formatter)
        self.assertIs(logger.handlers[0].formatter, formatter)

    def test_06_module_logger_sync(self) -> None:
        """Module-level LOGGER tracks the default-name singleton."""
        get_logger()
        self.assertIs(tm.LOGGER, get_logger())

    def test_07_default_level(self) -> None:
        """Level defaults to module LOG_LEVEL (logging.INFO)."""
        logger = get_logger(name='tm_default_level')
        self.assertEqual(logger.level, LOG_LEVEL)
        self.assertEqual(LOG_LEVEL, logging.INFO)


# ---------------------------------------------------------------------------
# DuplicateWarningFilter
# ---------------------------------------------------------------------------

class TestDuplicateWarningFilter(unittest.TestCase):
    """Contract: each WARNING message passes exactly once; all other levels
    always pass.

    Expected behavior:
        - first occurrence of a WARNING message passes;
        - identical WARNING text afterwards is dropped;
        - non-WARNING records are never inspected or dropped.
    """

    @classmethod
    def setUpClass(cls):
        cls.filter_ = DuplicateWarningFilter()

    def test_00_non_warning_passes(self) -> None:
        """INFO and ERROR records always pass."""
        self.assertTrue(self.filter_.filter(_make_record(logging.INFO, 'info')))
        self.assertTrue(self.filter_.filter(_make_record(logging.ERROR, 'error')))

    def test_01_first_warning_passes(self) -> None:
        """First occurrence of a WARNING message passes."""
        self.assertTrue(self.filter_.filter(_make_record(logging.WARNING, 'warn once')))

    def test_02_duplicate_warning_dropped(self) -> None:
        """Identical WARNING text is dropped on the second occurrence."""
        self.assertTrue(self.filter_.filter(_make_record(logging.WARNING, 'warn twice')))
        self.assertFalse(self.filter_.filter(_make_record(logging.WARNING, 'warn twice')))

    def test_03_different_warning_passes(self) -> None:
        """A new WARNING message passes even after a duplicate check."""
        self.assertTrue(self.filter_.filter(_make_record(logging.WARNING, 'warn three')))

    def test_04_same_template_different_args(self) -> None:
        """Different formatted text is distinct even with a shared template."""
        self.assertTrue(self.filter_.filter(_make_record(logging.WARNING, 'warn %s', ('a',))))
        self.assertTrue(self.filter_.filter(_make_record(logging.WARNING, 'warn %s', ('b',))))


# ---------------------------------------------------------------------------
# ColoredFormatter
# ---------------------------------------------------------------------------

class TestColoredFormatter(unittest.TestCase):
    """Contract: format() wraps the message in per-level ANSI colors matching
    the upstream color scheme, while preserving custom fmt/datefmt/style.

    Expected behavior:
        - NOTSET -> plain, DEBUG -> blue, INFO -> green,
          WARNING -> yellow, ERROR -> red, CRITICAL -> bold red;
        - non-multiple-of-10 levels fall into the bucket above them.
    """

    @classmethod
    def setUpClass(cls):
        cls.formatter = ColoredFormatter()

    def _color_of(self, levelno: int) -> str:
        return self.formatter.format(_make_record(levelno, 'msg'))

    def test_00_level_colors(self) -> None:
        """Each standard level maps to its documented ANSI color."""
        cases = {
            logging.NOTSET: '',
            logging.DEBUG: '\33[34;1m',
            logging.INFO: '\33[32;1m',
            logging.WARNING: '\33[33;1m',
            logging.ERROR: '\33[31;1m',
            logging.CRITICAL: '\33[31;1;3;4m',
        }
        for levelno, prefix in cases.items():
            out = self._color_of(levelno)
            self.assertTrue(out.startswith(prefix), f'level {levelno}: unexpected prefix {out[:20]!r}')
            if prefix:
                self.assertTrue(out.endswith('\33[0m'))

    def test_01_mid_level_buckets(self) -> None:
        """Non-standard levels use the bucket above them."""
        self.assertTrue(self._color_of(5).startswith('\33[34;1m'))    # 5 -> blue
        self.assertTrue(self._color_of(25).startswith('\33[33;1m'))   # 25 -> yellow
        self.assertTrue(self._color_of(45).startswith('\33[31;1;3;4m'))  # 45 -> bold red
        self.assertFalse(self._color_of(0).startswith('\33['))        # 0 -> plain

    def test_02_format_contents(self) -> None:
        """Output contains level name, record name, module:lineno and message."""
        out = self.formatter.format(_make_record(logging.INFO, 'hello from test'))
        self.assertIn('INFO', out)
        self.assertIn('test.telemetrics', out)
        self.assertIn('test_telemetrics:1', out)
        self.assertIn('hello from test', out)

    def test_03_custom_fmt_and_style(self) -> None:
        """'%' style custom format renders exactly the wrapped text."""
        formatter = ColoredFormatter(fmt='%(levelname)s|%(message)s', style='%')
        out = formatter.format(_make_record(logging.INFO, 'plain'))
        self.assertEqual(out, '\33[32;1mINFO|plain\33[0m')

    def test_04_custom_datefmt(self) -> None:
        """Custom datefmt controls the asctime field."""
        formatter = ColoredFormatter(datefmt='%Y-%m-%d')
        out = formatter.format(_make_record(logging.INFO, 'dated'))
        expected = time.strftime('%Y-%m-%d', time.gmtime())
        self.assertIn(expected, out)


if __name__ == '__main__':
    unittest.main()
