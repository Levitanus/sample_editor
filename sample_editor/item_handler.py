"""Contains classes for manipulating of Reaper Items."""
from pathlib import Path
import typing as ty

import reapy as rpr

import librosa as lr
import numpy as np


class ItemsError(Exception):
    ...


@rpr.inside_reaper()
def _select_items_in_ts(pr: rpr.Project) -> None:
    if len(pr.selected_tracks):
        rpr.perform_action(40718)  # select all items on track in ts
    else:
        rpr.perform_action(40717)  # select all items in ts


class ItemHandler:
    """General Reaper Item handler.

    Used for managing its audiodata and tracks bounds.

    Attributes
    ----------
    item : reapy.Item
    last_filename : str
        last seen source filename (without path)
    last_path : str
        last seen source file directory
    pr : reapy.Project
    sr : int
        samplerate
    """

    def __init__(
        self, sr: int = 22050, item: ty.Optional[rpr.Item] = None
    ) -> None:
        """
        Parameters
        ----------
        sr : int, optional
            Samplerate
        item : Optional[rpr.Item]
            If None — gets the first selected item in time selection.
        """
        self.sr = sr
        self.pr = rpr.Project()
        self.last_filename = ''
        self.last_path = ''
        self.item = self._get_item() if item is None else item

    def __repr__(self) -> str:
        return "ItemHandler(sr={sr}, item={item})".format(
            sr=self.sr, item=self.item
        )

    def get_item_bounds_within_ts(self) -> ty.Tuple[float, float]:
        """Get start time and duration of processed area of item.

        Returns
        -------
        Tuple[float, float]
            start, duration
        """
        ts = self.pr.time_selection
        i_pos = self.item.position
        i_length = self.item.length
        if ts.start > 0 and i_pos < ts.start:
            start = ts.start
        else:
            start = i_pos
        if ts.end < i_length + i_pos and ts.start != ts.end:
            duration = ts.end - start
        else:
            duration = i_length
        return start, duration

    def _get_item_bounds(self) -> ty.Tuple[float, float]:
        """
        Returns
        -------
        Tuple[float, float]
            offset, duration
        """
        start, duration = self.get_item_bounds_within_ts()
        offset = start - self.item.position + self.take.start_offset
        return offset, duration

    @rpr.inside_reaper()
    def _get_item(self) -> rpr.Item:
        try:
            return self.pr.selected_items[0]
        except Exception as e:
            if 'IndexError' not in str(e) + str(type(e)):
                print(str(e) + str(type(e)))
                raise e
            _select_items_in_ts(self.pr)  # select all items in ts
            return self.pr.selected_items[0]

    @property
    def take(self) -> rpr.Take:  # type:ignore
        with rpr.inside_reaper():
            return self.item.active_take

    @property
    def source(self) -> rpr.Source:  # type:ignore
        with rpr.inside_reaper():
            return self.take.source

    @property
    def path(self) -> str:
        with rpr.inside_reaper():
            self.last_path = str(Path(self.source.filename).parent)
            return self.last_path
        raise NotImplementedError()

    @property
    def filename(self) -> str:
        with rpr.inside_reaper():
            self.last_filename = self.take.name
            return self.last_filename
        raise NotImplementedError()

    @property
    def vol(self) -> float:
        with rpr.inside_reaper():
            i_v = self.item.get_info_value("D_VOL")
            t_v = self.take.get_info_value("D_VOL")
        return i_v * t_v

    def load_audio(self, reaper_vol: bool = True) -> ty.Iterable[float]:
        """Get np.array of Item audiodata in mono.

        Parameters
        ----------
        reaper_vol : bool, optional
            Default to True
            Sohuld audio be normalized to the Reaper item*take level or not

        Returns
        -------
        ty.Iterable[float]

        """
        with rpr.inside_reaper():
            source = self.source
            filename = source.filename
            sr = self.sr
            offset, duration = self._get_item_bounds()
        loaded = lr.load(
            filename,
            sr=sr,
            mono=True,
            offset=offset,
            duration=duration,
        )[0]
        if reaper_vol:
            loaded *= self.vol
        return loaded  # type:ignore


class ItemsHandler:
    """Handles multiple ItemHandler objects.

    Used to make operations on multiple items easy.

    Attributes
    ----------
    item_handlers : List[ItemHandler]
    pr : reapy.Project
    sr : int
        samplerate
    """

    def __init__(
        self,
        sr: int = 22050,
        item_handlers: ty.Optional[ty.List[ItemHandler]] = None,
        split_at_ts: bool = False
    ) -> None:
        """
        Parameters
        ----------
        sr : int, optional
            Samplerate
        item_handlers : Optional[List[ItemHandler]]
            If None — any items in time selection are Used
        split_at_ts : bool, optional
            If True — items are split at time selection
        """
        if split_at_ts:
            # Item: Split item_handlers at time selection
            rpr.perform_action(40061)
        self.sr = sr
        self.pr = rpr.Project()
        self.item_handlers = self._get_items(
        ) if item_handlers is None else item_handlers

    @rpr.inside_reaper()
    def _get_items(self) -> ty.List[ItemHandler]:
        if not len(self.pr.selected_items):
            _select_items_in_ts(self.pr)
        return [
            ItemHandler(sr=self.sr, item=item)
            for item in self.pr.selected_items
        ]

    def split(self,
              position: float) -> ty.Tuple['ItemsHandler', 'ItemsHandler']:
        """Split items and return a couple of handlers.

        Parameters
        ----------
        position : float

        Returns
        -------
        Tuple['ItemsHandler', 'ItemsHandler']
            left, right
        """
        itms_l: ty.List[ItemHandler] = []
        itms_r: ty.List[ItemHandler] = []
        for item in self.item_handlers:
            il, ir = item.item.split(position)
            itms_l.append(ItemHandler(sr=self.sr, item=il))
            itms_r.append(ItemHandler(sr=self.sr, item=ir))
        return ItemsHandler(sr=self.sr, item_handlers=itms_l), ItemsHandler(
            sr=self.sr, item_handlers=itms_r
        )

    def make_copy(
        self,
        position: float,
        length: ty.Optional[float] = None,
        additional_source_offset: float = 0.0,
    ) -> 'ItemsHandler':
        """Make copy of items and place them at position.

        Parameters
        ----------
        position : float
        length : Optional[float]
        additional_source_offset : float, optional
            If not 0.0 — source is shifted for each active take of each item
        """
        if not self.are_bounds_identical:
            raise ItemsError('bounds of items are not identical')
        new_i_hndlrs: ty.List[ItemHandler] = []
        for ih in self.item_handlers:
            old_item = ih.item
            old_take = old_item.active_take
            length = old_item.length if length is None else length
            new_item = old_item.track.add_item(start=position, length=length)
            new_item.set_info_value("D_VOL", old_item.get_info_value("D_VOL"))
            new_take = new_item.add_take()
            new_take.set_info_value("D_VOL", old_take.get_info_value("D_VOL"))
            new_take.source = old_take.source
            new_take.start_offset = (
                old_take.start_offset + additional_source_offset
            )
            new_i_hndlrs.append(ItemHandler(sr=self.sr, item=new_item))
        return ItemsHandler(sr=self.sr, item_handlers=new_i_hndlrs)

    def delete(self) -> None:
        """Delete all items."""
        for item in self.item_handlers:
            item.item.delete()

    def get_bounds(
        self,
        check_for_indentity: bool = False,
        count_ts: bool = False
    ) -> ty.Tuple[float, float]:
        """Get bounds of items.

        Parameters
        ----------
        check_for_indentity : bool, optional
            If bounds should be Identical.
        count_ts : bool, optional
            If should count time selection as bound, default to False.

        Returns
        -------
        ty.Tuple[float, float]
            left, right

        Raises
        ------
        ItemsError
            If bounds are not identical and check_for_identity is False
        """
        if check_for_indentity and not self.are_bounds_identical:
            raise ItemsError('bounds of items are not identical')
        left, right = (-1.0, -1.0)
        for ih in self.item_handlers:
            position = ih.item.position
            length = ih.item.length
            if position < left or left == -1.0:
                left = position
            if position + length > right:
                right = position + length
        if count_ts:
            ts = self.pr.time_selection
            if ts.start == ts.end:
                return left, right
            ts_l, ts_r = ts.start, ts.end
            left = max(left, ts_l)
            right = min(right, ts_r)
        return left, right

    @property
    def are_bounds_identical(self) -> bool:
        """Whether item start and end are identical.

        :type: bool
        """
        pos, length = None, None
        for i_h in self.item_handlers:
            item = i_h.item
            if (pos, length) == (None, None):
                pos, length = item.position, item.length
                continue
            if (pos, length) != (item.position, item.length):
                return False
        return True

    @property
    def position(self) -> float:
        return self.item_handlers[0].item.position

    @position.setter
    def position(self, position: float) -> None:
        for i_h in self.item_handlers:
            i_h.item.position = position

    @property
    def start_offset(self) -> float:
        return self.item_handlers[0].item.active_take.start_offset

    @start_offset.setter
    def start_offset(self, offset: float) -> None:
        with rpr.inside_reaper():
            for ih in self.item_handlers:
                ih.item.active_take.start_offset = offset

    @property
    def length(self) -> float:
        return self.item_handlers[0].item.length

    @length.setter
    def length(self, length: float) -> None:
        for i_h in self.item_handlers:
            i_h.item.length = length

    def get_longest_items_on_each_track(self) -> 'ItemsHandler':
        items: ty.Dict[str, ItemHandler] = {}
        for ih in self.item_handlers:
            tr = ih.item.track.id
            if tr in items:
                if ih.item.length < items[tr].item.length:
                    continue
            items[tr] = ih
        return ItemsHandler(self.sr, list(items.values()))

    def load_audio(self,
                   mono: bool = True,
                   reaper_vol: bool = True) -> ty.List[ty.Iterable[float]]:
        """Load audio of items to the np.array.

        Parameters
        ----------
        mono : bool, optional
            Default to True
        reaper_vol : bool, optional
            Default to True
            Sohuld audio be normalized to the Reaper item*take level or not

        Returns
        -------
        ty.Iterable[ty.Iterable[float]]

        Raises
        ------
        ItemsError
            If items are not identical
        """
        with rpr.inside_reaper():
            items_handler = self
            if not self.are_bounds_identical:
                items_handler = self.get_longest_items_on_each_track()
                if not items_handler.are_bounds_identical:
                    raise ItemsError('bounds of items are not identical')
            audios: ty.List[ty.Iterable[float]] = []
            for ih in items_handler.item_handlers:
                y = ih.load_audio(reaper_vol=reaper_vol)
                audios.append(y)
        if mono:
            return [np.sum(audios, 0)]
        return np.column_stack(audios)  # type:ignore

    def fade_in(self, length: float, shape: int = 0) -> None:
        with rpr.inside_reaper():
            for i_h in self.item_handlers:
                i_h.item.set_info_value('D_FADEINLEN', length)
                i_h.item.set_info_value('C_FADEINSHAPE', shape)

    def fade_out(self, length: float, shape: int = 0) -> None:
        with rpr.inside_reaper():
            for i_h in self.item_handlers:
                i_h.item.set_info_value('D_FADEOUTLEN', length)
                i_h.item.set_info_value('C_FADEOUTSHAPE', shape)
