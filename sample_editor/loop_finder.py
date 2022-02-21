import typing as ty

import reapy_boost as rpr

import librosa as lr
import numpy as np

from .item_handler import ItemsHandler


class LoopError(Exception):
    ...


class LoopFinder:

    def __init__(
        self,
        item_handler: ItemsHandler,
    ) -> None:
        self._handler = item_handler
        self.sr = self._handler.sr

    def load_audio(self) -> ty.Iterable[float]:
        return self._handler.load_audio(mono=True)[0]  # type:ignore

    def _find_best_start_idxes(
        self, ar: np.array, slide_wind_spl: int, corr_wind_spl: int,
        corr_treshold: float
    ) -> ty.Tuple[float, int]:
        out = np.zeros(slide_wind_spl, float)

        # print(-e_ofst, -(e_ofst + corr_wind_spl), len(ar))
        for i in range(slide_wind_spl):
            # print(i, corr_wind_spl, i + corr_wind_spl)
            # print(ar)
            start = ar[i:i + corr_wind_spl]
            end = ar[-(i + corr_wind_spl
                       ):-i] if i > 0 else ar[-(i + corr_wind_spl):]
            # print(start, end)
            out[i] = np.corrcoef(start, end)[0][1]
            if out[i] >= corr_treshold:
                break

        max_i = np.argmax(out)
        return out[max_i], max_i

    def _find_best_tail_pos(
        self, ar: np.array, s_w_spl: int, c_w_spl: int, s_ofst: int,
        corr_treshold: float
    ) -> ty.Tuple[float, int]:
        out = np.zeros(s_w_spl, float)

        start = ar[s_ofst:s_ofst + c_w_spl]
        for i in range(s_w_spl):
            end = ar[-(i + c_w_spl):-i] if i > 0 else ar[-(i + c_w_spl):],
            out[i] = np.corrcoef(start, end)[0][1]
            if out[i] >= corr_treshold:
                break

        max_i = np.argmax(out)
        return out[max_i], max_i

    def _find_best_start_pos(
        self, ar: np.array, s_w_spl: int, c_w_spl: int, e_ofst: int,
        corr_treshold: float
    ) -> ty.Tuple[float, int]:
        out = np.zeros(s_w_spl, float)

        # print(-e_ofst, -(e_ofst + c_w_spl), len(ar))
        end = ar[-(e_ofst + c_w_spl):-e_ofst]
        for i in range(s_w_spl):
            start = ar[i:i + c_w_spl]
            # print(start, end)
            out[i] = np.corrcoef(start, end)[0][1]
            if out[i] >= corr_treshold:
                break

        max_i = np.argmax(out)
        return out[max_i], max_i

    def get_loop(
        self,
        corr_wind_sec: float,
        slide_wind_sec: float,
        # crossfade_length: float,
        corr_treshold: float = 0.965,
        corr_min_treshold: float = 0.86,
    ) -> ty.Tuple[float, float]:
        """Get loop start and end points in seconds.

        Parameters
        ----------
        corr_wind_sec : float
            How long the start and end should look seem.
        slide_wind_sec : float
            How large looking area is
        corr_treshold : float, optional
            How close should be start and end: 1.0 is exactly the same.
        corr_min_treshold : float, optional
            Which correlation counted as total fail.

        Returns
        -------
        Tuple[float, float]
            start, end
        """
        ar = self.load_audio()
        corr_wind_spl = lr.core.time_to_samples(corr_wind_sec, sr=self.sr)
        slide_wind_spl = lr.core.time_to_samples(slide_wind_sec, sr=self.sr)
        print('sample values:', corr_wind_spl, slide_wind_spl)

        best_corr, start_idx = self._find_best_start_idxes(
            ar, slide_wind_spl, corr_wind_spl, corr_treshold=corr_treshold
        )
        print(best_corr, start_idx)
        max_tries = 20
        last_s, last_e = 0, 0
        for i in range(max_tries):
            print(f'try {i}')
            e_corr, e_idx = self._find_best_tail_pos(
                ar,
                slide_wind_spl,
                corr_wind_spl,
                s_ofst=start_idx,
                corr_treshold=corr_treshold
            )
            print(e_corr, e_idx)
            s_corr, start_idx = self._find_best_start_pos(
                ar,
                slide_wind_spl,
                corr_wind_spl,
                e_ofst=e_idx,
                corr_treshold=corr_treshold
            )
            print(s_corr, start_idx)
            if last_s == start_idx and last_e == e_idx:
                break
            if s_corr >= corr_treshold:
                break
            last_s, last_e = start_idx, e_idx
        if s_corr < corr_min_treshold:
            raise LoopError(
                (
                    f'correlation with this selection is {s_corr}. '
                    f'Which is below the target quality: {corr_min_treshold}'
                )
            )

        time_st = lr.samples_to_time(start_idx, sr=self.sr)
        time_end = lr.samples_to_time(e_idx + corr_wind_spl, sr=self.sr)
        # self._cut_and_fade(time_st, time_end, crossfade_length)
        return time_st, time_end


class LoopSlicer:

    def __init__(
        self, items_handler: ItemsHandler, loop_finder: LoopFinder
    ) -> None:
        self._handler = items_handler
        self._finder = loop_finder
        self._pr = self._handler.pr

    def cut_and_fade(
        self,
        st_ofst: float,
        end_ofst: float,
        crs_length: float = .1,
        crs_shape: int = 0,
    ) -> rpr.Region:
        """Cut and fade items to make loop.

        Note
        ----
        units in seconds

        Parameters
        ----------
        st_ofst : float
            Start offset from time selection
        end_ofst : float
            End offset from time selection
        crs_length : float, optional
            Crossfade length

        Returns
        -------
        reapy.Region
            loop region
        """
        with rpr.inside_reaper():
            self._pr.begin_undo_block()
            region_ofst = 0.1
            start, duration = self._handler.item_handlers[
                0].get_item_bounds_within_ts()

            main_part, tail = self._handler.split(start + duration - end_ofst)
            tail.position += end_ofst + region_ofst
            tail.start_offset += end_ofst
            tail.length -= end_ofst + region_ofst

            end_part = main_part.make_copy(main_part.position)
            del_part, end_part = end_part.split(start + st_ofst)
            del_part.delete()

            end_part.position += duration - st_ofst - end_ofst
            end_part.length = crs_length + region_ofst

            main_part.length += crs_length
            reg = self._pr.add_region(
                start + st_ofst + end_part.length,
                end_part.position + end_part.length,
                color=0xff0000,
                name='#'
            )
            self._pr.loop_points = (
                start + st_ofst + end_part.length,
                end_part.position + end_part.length
            )
            main_part.fade_out(crs_length, crs_shape)
            end_part.fade_in(crs_length, crs_shape)
            self._pr.end_undo_block('cut and fade loop')
        return reg

    def cut_and_fade_deprecated(
        self,
        st_ofst: float,
        end_ofst: float,
        crs_length: float = .1
    ) -> rpr.Region:
        """Cut and fade items to make loop.

        Note
        ----
        units in seconds

        Parameters
        ----------
        st_ofst : float
            Start offset from time selection
        end_ofst : float
            End offset from time selection
        crs_length : float, optional
            Crossfade length

        Returns
        -------
        reapy.Region
            loop region
        """
        with rpr.inside_reaper():
            self._pr.begin_undo_block()
            region_ofst = 0.1
            start, duration = self._handler.item_handlers[
                0].get_item_bounds_within_ts()
            itms_hdlr_l, itms_hdlr_r = self._handler.split(start + st_ofst)
            _, del_part = itms_hdlr_r.split(start + duration - end_ofst)
            del_part.delete()
            itms_hdlr_end = itms_hdlr_r.make_copy(
                itms_hdlr_r.position + itms_hdlr_r.length,
                length=crs_length + region_ofst
            )
            itms_hdlr_r.length += crs_length
            reg = self._pr.add_region(
                itms_hdlr_r.position + itms_hdlr_end.length,
                itms_hdlr_end.position + itms_hdlr_end.length,
                color=0xff0000,
                name='#'
            )
            self._pr.loop_points = (
                itms_hdlr_r.position + itms_hdlr_end.length,
                itms_hdlr_end.position + itms_hdlr_end.length
            )
            itms_hdlr_r.fade_out(crs_length)
            itms_hdlr_end.fade_in(crs_length)
            self._pr.end_undo_block('cut and fade loop')
        return reg
