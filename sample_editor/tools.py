from enum import Enum, auto
import math
import typing as ty
import reapy_boost as rpr
from types import TracebackType
import librosa as lr


class LengthUnit(Enum):
    samples = auto()
    ms = auto()
    frames = auto()


def length_convert(
    length: float,
    sr: int,
    units_def: LengthUnit,
    units_target: LengthUnit,
    hop_length: int = 512
) -> float:
    """Convert length from one unit to another.

    Parameters
    ----------
    length : float
        in sec
    sr : int
    units_def : LengthUnit
        Units that are passed
    units_target : LengthUnit
        Units that are expected
    hop_length : int, optional
        512 by default, mandatory for frames conversion

    Returns
    -------
    float
    """
    if units_def == LengthUnit.samples:
        if units_target == LengthUnit.frames:
            return lr.samples_to_frames(length, hop_length)  # type:ignore
        if units_target == LengthUnit.ms:
            return lr.samples_to_time(length, sr)  # type:ignore
        return length
    if units_def == LengthUnit.ms:
        if units_target == LengthUnit.samples:
            return lr.time_to_samples(length, sr)  # type:ignore
        if units_target == LengthUnit.frames:
            return lr.time_to_frames(length, sr, hop_length)  # type:ignore
        return length
    if units_def == LengthUnit.frames:
        if units_target == LengthUnit.samples:
            return lr.frames_to_samples(length, hop_length)  # type:ignore
        if units_target == LengthUnit.ms:
            return lr.frames_to_time(length, sr, hop_length)  # type:ignore
        return length
    raise TypeError(f'not a LengthUnit: {units_def, units_target}')


@ty.overload
def hz_to_note(freq: float) -> str:
    ...


@ty.overload
def hz_to_note(freq: ty.Iterable[float]) -> ty.List[str]:
    ...


def hz_to_note(
    freq: ty.Union[float, ty.Iterable[float]]
) -> ty.Union[str, ty.List[str]]:
    """Fork of librosa.hz_to_note with correct '#' symbol.

    Parameters
    ----------
    freq : Union[float, Iterable[float]]
        freq in hz

    Returns
    -------
    Union[str, List[str]]
        Note name in format "C#2". Middle C is "C4".
    """
    result = ty.cast(ty.Union[str, ty.List[str]], lr.hz_to_note(freq))
    if isinstance(result, ty.List):
        return [note.replace('♯', '#') for note in result]
    return result.replace('♯', '#')
