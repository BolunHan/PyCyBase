__version__ = '0.1.11.post2'

import ctypes
import functools
import os
import pathlib
from collections.abc import Mapping

# shm_open/shm_unlink live in librt on glibc < 2.34 (e.g. manylinux_2_28) and in
# libc on newer glibc. Extensions embedding cbase's allocator headers reference
# them without linking librt; promoting librt to the dynamic linker's global
# scope (same pattern as algo_engine.exchange_profile's RTLD_GLOBAL preload)
# makes those symbols resolvable by every extension loaded after this package.
# No-op on glibc >= 2.34 (librt is an empty stub) and where librt is absent.
_RTLD_GLOBAL = getattr(ctypes, 'RTLD_GLOBAL', 0)
if _RTLD_GLOBAL:
    try:
        ctypes.CDLL('librt.so.1', mode=_RTLD_GLOBAL)
    except Exception:
        pass  # graceful fallback: symbols are provided by libc on modern systems

from .config_view import CONFIG_VIEW
from .backports.telemetrics import get_logger

LOGGER = get_logger(name='PyCyBase')


def _format_config_view(config: Mapping, indent: int = 0) -> str:
    """Render a (possibly nested) config view as indented bullet lines."""
    lines = []
    for key, value in config.items():
        if isinstance(value, Mapping):
            lines.append(f"{'  ' * indent}- {key}:")
            lines.append(_format_config_view(value, indent + 1))
        else:
            lines.append(f"{'  ' * indent}- {key}: {value}")
    return "\n".join(lines)


@functools.cache
def get_include() -> list[str]:
    res_dir = pathlib.Path(__file__).parent
    LOGGER.info(
        f'Building with <PyCyBase> version: "{__version__}", resource directory: "{res_dir}", '
        f"config:\n{_format_config_view(CONFIG_VIEW)}"
    )

    src_dirs = [
        os.path.realpath(res_dir),
        os.path.realpath(res_dir / 'allocator_protocol'),
        os.path.realpath(res_dir / 'bytemap'),
        os.path.realpath(res_dir / 'intern_string'),
    ]

    include_root = os.path.realpath(res_dir / 'includes')
    if os.path.isdir(include_root):
        src_dirs.append(include_root)

    return src_dirs


__all__ = [
    'get_include',
    'CONFIG_VIEW',
]
