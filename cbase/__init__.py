__version__ = '0.1.2'

import functools
import os
import pathlib


@functools.cache
def get_include() -> list[str]:
    res_dir = pathlib.Path(__file__).parent

    src_dirs = [
        os.path.realpath(res_dir),
        os.path.realpath(res_dir / 'allocator_protocol'),
    ]

    include_root = os.path.realpath(res_dir / 'includes')
    if os.path.isdir(include_root):
        src_dirs.append(include_root)

    return src_dirs


__all__ = [
    'get_include',
]
