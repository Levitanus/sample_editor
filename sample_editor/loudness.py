import typing as ty

import reapy as rpr
import librosa as lr
import numpy as np
import math

from .item_handler import ItemsHandler


def amplitude_to_db(amplitude: float) -> float:
    return 20 * math.log10(amplitude)


def db_to_amplitude(db: float) -> float:
    return 10**(db / 20)


def _get_entire_rms(audio: ty.Iterable[float]) -> float:
    square = np.square(audio)
    mean = np.mean(square)
    root = math.sqrt(mean)
    return root


def get_rms(items_handler: ItemsHandler, median: bool = False) -> float:
    """Compute RMS of items audio.

    Parameters
    ----------
    items_handler : ItemsHandler
    median : bool, optional
        Default to False. If needed not entire RMS but median value.
    """
    audio = items_handler.load_audio()[0]
    if not median:
        return _get_entire_rms(audio)
    rms = lr.feature.rms(y=audio)
    median_rms = ty.cast(float, np.median(rms))
    return median_rms


def get_first_rms_value_ms(
    items_handler: ItemsHandler,
    rms_target: float,
    want_marker: ty.Optional[str] = None
) -> float:
    """Get time in ms of the first rms value above target rms.

    Parameters
    ----------
    items_handler : ItemsHandler
    rms_target : float
    want_marker : ty.Optional[str], optional
        if None — no marker placed, if string — maker with name is placed
    items_handler : ItemsHandler
    """
    audio = items_handler.load_audio()[0]
    rms = lr.feature.rms(y=audio)[0]
    for index, val in enumerate(rms):
        if val >= rms_target:
            break
        if index == len(rms):
            raise ValueError('no rms above target')
    ms = ty.cast(float, lr.frames_to_time(index, items_handler.sr))
    if want_marker:
        rpr.Project().add_marker(
            items_handler.position + ms, name=want_marker, color=0x00ff00
        )
    return ms


def get_last_rms_value_ms(
    items_handler: ItemsHandler,
    rms_target: float,
    want_marker: ty.Optional[str] = None
) -> float:
    """Get time in ms of the first rms value above target rms.

    Parameters
    ----------
    items_handler : ItemsHandler
    rms_target : float
    want_marker : ty.Optional[str], optional
        if None — no marker placed, if string — maker with name is placed
    items_handler : ItemsHandler
    """
    audio = items_handler.load_audio()[0]
    rms = lr.feature.rms(y=audio)[0]
    for index, val in enumerate(reversed(rms)):
        if val >= rms_target:
            break
        if index == len(rms):
            raise ValueError('no rms above target')
    # print(index, val)
    ms = ty.cast(float, lr.frames_to_time(len(rms) - index, items_handler.sr))
    if want_marker:
        rpr.Project().add_marker(
            items_handler.position + ms, name=want_marker, color=0x00ff00
        )
    return ms
