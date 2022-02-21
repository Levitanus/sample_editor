import typing as ty

import reapy_boost as rpr
import librosa as lr
import numpy as np
import math

from .item_handler import ItemsHandler
from .tools import LengthUnit


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
    want_marker: ty.Optional[str] = None,
    below: bool = False,
    start_offset: ty.Optional[float] = None,
    end_offset: ty.Optional[float] = None,
    direction: str = 'right',
    want_trend: bool = False,
    hop_length_spl: int = 512,
) -> float:
    """Get time in ms of the first rms value above target rms.

    Parameters
    ----------
    items_handler : ItemsHandler
    rms_target : float
    want_marker : ty.Optional[str], optional
        if None — no marker placed, if string — maker with name is placed
    below : bool, optional
        return first value lower than target, False by default
    start_offset : ty.Optional[float], optional
        If specified, ms are counted from start offset.
    end_offset : ty.Optional[float], optional
        If specified, ms are counted from or up to the low_offset
    direction : str, optional
        Can be either 'right' or 'left'
    want_trend : bool, optional
        if True (False by default) — will loof for two frames
        abowe or below the target

    Returns
    -------
    float
        start offset from search area
    """
    audio = items_handler.load_audio()[0]
    if start_offset:
        st_ofst_spl = lr.time_to_samples(start_offset, items_handler.sr)
        audio = audio[st_ofst_spl:]  # type:ignore
    if end_offset:
        end_ofst_spl = lr.time_to_samples(end_offset, items_handler.sr)
        if start_offset:
            end_ofst_spl -= st_ofst_spl
        audio = audio[:end_ofst_spl]  # type:ignore
    rms = lr.feature.rms(y=audio, hop_length=hop_length_spl)[0]
    # print('RMS', rms, rms[::-1], sep='\n--')
    if direction == 'right':
        enum_ = enumerate(rms)
    if direction == 'left':
        enum_ = enumerate(rms[::-1])
    else:
        raise TypeError(
            f'direction can be only "right" or "left". Here is: {direction}'
        )
    has_one = False
    for index, val in enum_:
        if val >= rms_target and not below:
            if has_one or not want_trend:
                break
            has_one = True
            continue
        if val <= rms_target and below:
            if has_one or not want_trend:
                break
            has_one = True
            continue
        has_one = False
        # if index == len(rms):
        #     raise ValueError('no rms above target')
    if want_trend and index > 0:
        index -= 1
    ms = ty.cast(
        float,
        lr.frames_to_time(index, items_handler.sr, hop_length=hop_length_spl)
    )
    # print(ms, index)
    if want_marker:
        i_left, i_right = items_handler.get_bounds(count_ts=True)
        if direction == 'right':
            position = i_left + ms
            if start_offset:
                position += start_offset
        if direction == 'left':
            if not end_offset:
                position = i_right - ms
                print('not end_offset, position={}'.format(position))
            else:
                position = i_left + end_offset - ms
                print('position={}'.format(position))
        rpr.Project().add_marker(position, name=want_marker, color=0x00ff00)
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


def detect_onsets(
    items_handler: ItemsHandler,
    pre_max: float,
    wait: float,
    fmin: ty.Optional[int] = None,
    pre_avg: ty.Optional[float] = None,
    post_max: ty.Optional[float] = None,
    post_avg: ty.Optional[float] = None,
    delta: float = 1.0,
    onset_markers: str = '',
    backtrack_markers: str = '',
    units: LengthUnit = LengthUnit.ms,
) -> ty.Tuple[ty.List[float], ty.List[float], ty.List[float]]:
    """Detect onsets and place markers if needed.

    Parameters
    ----------
    items_handler : ItemsHandler
    pre_max : float
        time to seek peacks before onset
    wait : float
        time to skip after detected onset
    fmin : ty.Optional[int], optional
        minimum frequency if filtering is needed
    pre_avg : ty.Optional[float], optional
        time to seek mean before offset (if None — pre_max is used)
    post_max : ty.Optional[float], optional
        time so seek peak after offset (if None — wait or post_avg are used)
    post_avg : ty.Optional[float], optional
        time to seek mean after onset (if None — wait of post_max are used)
    delta : float, optional
        threshold offset for mean (ambiguos parameter)
    onset_markers : str, optional
        If not null string — markers with the same name will be placed
    backtrack_markers : str, optional
        If not null string — markers with the same name will be placed
    units : LengthUnit, optional
        length units for onsets and backtrack return (ms are default)

    Returns
    -------
    Tuple[List[float], List[float], List[float]]
        onsets, backtracks, onset_envelope(in frames)
    """
    with rpr.inside_reaper():
        audio = items_handler.load_audio()[0]
        sr = items_handler.sr
        if fmin:
            Spc = lr.feature.mfcc(audio, sr, fmin=fmin)
            onset_envelope = lr.onset.onset_strength(sr, S=Spc)
        else:
            onset_envelope = lr.onset.onset_strength(audio, sr)
        if post_avg is None and post_max is None:
            post_max, post_avg = wait, wait
        if post_avg is None:
            post_avg = post_max
        if post_max is None:
            post_max = post_avg
        if pre_avg is None:
            pre_avg = pre_max
        (pre_max, wait, pre_avg, post_max, post_avg) = lr.time_to_frames(
            (pre_max, wait, pre_avg, post_max, post_avg), sr
        )
        onsets = lr.util.peak_pick(
            onset_envelope,
            pre_max,
            post_max,
            pre_avg,
            post_avg,
            delta,
            wait,
        )
        backtrack = lr.onset.onset_backtrack(onsets, onset_envelope)
        if backtrack_markers:
            for bck in lr.frames_to_time(backtrack, sr=sr):
                pos = items_handler.get_bounds(count_ts=True)[0] + bck
                rpr.Project().add_marker(pos, name=backtrack_markers)
        if onset_markers:
            for onst in lr.frames_to_time(onsets, sr=sr):
                pos = items_handler.get_bounds(count_ts=True)[0] + onst
                rpr.Project().add_marker(pos, name=onset_markers)
        if units == LengthUnit.ms:
            onsets, backtrack = (
                lr.frames_to_time(onsets,
                                  sr), lr.frames_to_time(backtrack, sr)
            )
        if units == LengthUnit.samples:
            onsets, backtrack = (
                lr.frames_to_samples(onsets,
                                     sr), lr.frames_to_samples(backtrack, sr)
            )
    return onsets, backtrack, onset_envelope
