import typing as ty

import librosa as lr
import numpy as np

from .tools import LengthUnit, length_convert, hz_to_note
from .item_handler import ItemsHandler, ItemsError


class PitchError(ItemsError):
    ...


def estimate_entire_root(
    audio: np.array,
    sr: int,
    min_note: str = 'C1',
    max_note: str = 'C7',
    frame_length: float = 4096,
    win_length: ty.Optional[float] = None,
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
        frame_length = length_convert(
            frame_length, sr, LengthUnit.samples, LengthUnit.ms
        )
        # frame_length = sr * frame_length // 1000
        if win_length is not None:
            # win_length = sr * frame_length // 1000
            win_length = length_convert(
                win_length, sr, LengthUnit.samples, LengthUnit.ms
            )

    f0s, v_flag, v_prob = lr.pyin(
        audio,
        fmin=lr.note_to_hz(min_note),
        fmax=lr.note_to_hz(max_note),
        sr=sr,
        win_length=None if win_length is None else win_length,
        frame_length=frame_length,
    )

    clean = f0s[np.logical_not(~v_flag)]
    # print(list(hz_to_note(f0) for f0 in clean))
    median = ty.cast(float, np.median(clean))
    return hz_to_note(median)


def get_first_null_f0(
    items_handler: ItemsHandler,
    start_offset: float,
    min_duration: float,
    end_offset: ty.Optional[float] = None,
    min_note: str = 'C1',
    max_note: str = 'C7',
    frame_length: float = 2048,
    win_length: ty.Optional[float] = None,
    offset_units: LengthUnit = LengthUnit.ms,
    length_units: LengthUnit = LengthUnit.samples
) -> float:
    audio = items_handler.load_audio()[0]
    sr = items_handler.sr

    if length_units != LengthUnit.samples:
        if length_units != LengthUnit.ms:
            raise TypeError('length_units can be only of ms or samples')
        frame_length = length_convert(
            frame_length, sr, length_units, LengthUnit.samples
        )

        if win_length:
            win_length = length_convert(
                win_length, sr, length_units, LengthUnit.samples
            )
    hop_length = int(frame_length // 4)
    start_offset_int = ty.cast(
        int,
        length_convert(start_offset, sr, offset_units, LengthUnit.samples)
    )

    if start_offset_int:
        audio = audio[start_offset_int:]  # type:ignore
    if end_offset:
        end_offset_int = ty.cast(
            int,
            length_convert(end_offset, sr, offset_units, LengthUnit.samples)
        )
        audio = audio[:end_offset_int - start_offset_int]  # type:ignore
    min_duration_frms = length_convert(
        min_duration,
        sr,
        offset_units,
        LengthUnit.frames,
        hop_length=hop_length
    )
    fmin, fmax = lr.note_to_hz(min_note), lr.note_to_hz(max_note)
    f0s, v_flag, v_prob = lr.pyin(
        audio,
        fmin=fmin,
        fmax=fmax,
        sr=sr,
        win_length=None if win_length is None else win_length,
        frame_length=frame_length,
    )
    # print(list(zip(f0s, v_flag)))
    nulls = np.where(~v_flag)
    # print(nulls)
    for idx, val in enumerate(nulls[0]):
        # print(val)
        if val >= min_duration_frms:
            # print(val, v_flag[val + 1])
            if v_flag[val + 1]:
                # print(f'skipping {val}')
                continue
            break

    if val < 5:
        raise PitchError(
            f'Cannot find null f0 at the reasonable frame (>=5): {v_flag}'
        )
    val_normalized = length_convert(
        val, sr, LengthUnit.frames, offset_units, hop_length=hop_length
    )
    # print(val_normalized, )
    return start_offset + val_normalized