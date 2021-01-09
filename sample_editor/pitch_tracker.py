import typing as ty
from enum import Enum, auto

import librosa as lr
import numpy as np


class LengthUnit(Enum):
    samples = auto()
    ms = auto()


def estimate_entire_root(
    audio: np.array,
    sr: int,
    min_note: str = 'C1',
    max_note: str = 'C7',
    frame_length: int = 2048,
    win_length: ty.Optional[int] = None,
    length_units: LengthUnit = LengthUnit.samples
) -> str:
    """Get root note of the entire audio array.

    Parameters
    ----------
    audio : np.array
    sr : int
        Samplerate
    min_note : str, optional
        Middle C is 'C4'
    max_note : str, optional
    frame_length : int, optional
        Samples by default
    win_length : ty.Optional[int]
        Samples by default, None = frame_length/2
    length_units : LengthUnit, optional
        can be samples or ms

    Returns
    -------
    str: note name
    """
    if length_units is LengthUnit.ms:
        frame_length = sr * frame_length // 1000
        if win_length is not None:
            win_length = sr * frame_length // 1000
    f0s, v_flag, v_prob = lr.pyin(
        audio,
        fmin=lr.note_to_hz(min_note),
        fmax=lr.note_to_hz(max_note),
        sr=sr,
        win_length=None if win_length is None else win_length,
        frame_length=4096,
    )

    clean = f0s[np.logical_not(~v_flag)]
    median = np.median(clean)
    return lr.hz_to_note(median)  # type:ignore
