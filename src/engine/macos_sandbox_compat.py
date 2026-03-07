from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Iterator

_orig_is_file = Path.is_file


@contextlib.contextmanager
def suppress_sandbox_permission_errors() -> Iterator[None]:
    """Temporarily patch Path.is_file to suppress PermissionError.

    Scoped to a context manager so the patch is active only during
    Pydantic BaseSettings / dotenv probing, not globally for the
    entire process lifetime.
    """

    def _patched_is_file(self: Path) -> bool:
        try:
            return _orig_is_file(self)
        except PermissionError:
            return False

    Path.is_file = _patched_is_file  # type: ignore[method-assign]
    try:
        yield
    finally:
        Path.is_file = _orig_is_file  # type: ignore[method-assign]
