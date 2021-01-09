import math
import typing as ty
import reapy as rpr
from types import TracebackType


class InsideUndoContext:
    """Combines reapy context managers for insidee reaper and undo.

    Parameters
    ----------
    undo_name : str
        Undo block description.
    flags : int
        1: track configurations
        2: track FX
        4: track items
        8: project states
        16: freeze states
    """

    def __init__(self, undo_name: str, flags: int = 0) -> None:
        """
        Parameters
        ----------
        undo_name : str
            Undo block description.
        flags : int
            1: track configurations
            2: track FX
            4: track items
            8: project states
            16: freeze states
        """
        self._u_text = undo_name
        self._u_flags = flags

    def __enter__(self) -> 'InsideUndoContext':
        self._ir = rpr.inside_reaper()
        self._ub = rpr.undo_block(self._u_text, flags=self._u_flags)
        self._ir.__enter__()
        self._ub.__enter__()
        print('__enter__')
        return self

    def __exit__(
        self, exc_type: ty.Optional[ty.Type[BaseException]],
        value: ty.Optional[BaseException],
        traceback: ty.Optional[TracebackType]
    ) -> None:
        self._ir.__exit__(exc_type, value, traceback)
        self._ub.__exit__(exc_type, value, traceback)
        print('__exit__')