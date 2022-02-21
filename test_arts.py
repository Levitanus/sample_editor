import typing as ty
from warnings import warn
import PySimpleGUI as sg
from aenum import extend_enum
import reapy_boost as rpr

from sample_editor.item_handler import ItemsHandler, ItemHandler, ItemsError
from sample_editor.gui import (
    BaseArt, ValuesFilledType, Wildcard, WildcardDict, wildcard_in_tokens,
    ArtError, REGION_KEY, FADE_SHAPES, RegionContents
)
from sample_editor.loudness import (
    get_rms, get_first_rms_value_ms, get_last_rms_value_ms, amplitude_to_db,
    db_to_amplitude, detect_onsets
)
from sample_editor.pitch_tracker import (
    estimate_entire_root, get_first_null_f0
)
from sample_editor.tools import LengthUnit
from sample_editor import widgets

from pprint import pprint

for name, value in (('sul', '$sul'), ):
    try:
        extend_enum(Wildcard, name, value)
    except TypeError as e:
        warn(str(e))


class Trem(BaseArt):

    def __init__(self) -> None:
        self.ns = 'Trem_'
        self.sus_bt = sg.Button('sus region', key=self.ns + 'sus')
        self.sus_marker = sg.Check(
            'marker on hard attack', default=True, key=self.ns + 'sus_marker'
        )
        self.sus_want_cut = sg.Check(
            'want cut',
            default=True,
            key=self.ns + 'sus_want_cut',
            tooltip='if checked — part left to the sus will be erased'
        )

        self.rel_bt = sg.Button('cut release', key=self.ns + 'release_cut')
        self.rel_reg_bt = sg.Button(
            'release region', key=self.ns + 'release_region'
        )
        self.release_region_want_cut = sg.Check(
            'want cut', default=True, key=self.ns + 'release_region_want_cut'
        )

        self.dyn = sg.Combo(
            values=['ff', 'f', 'p', 'pp'],
            default_value='ff',
            key=self.ns + 'dyn',
        )
        self.sul = sg.Combo(
            values=['sulTop', 'SulBot'],
            default_value='sulBot',
            key=self.ns + 'sul',
        )
        silence_def = .1
        self.sus_silense_sl = sg.Slider(
            range=(-60, 0),
            resolution=.001,
            key=self.ns + 'sus_silence_treshold',
            tooltip='threshold in dB to count as sustain silence',
            # enable_events=True,
            default_value=silence_def,
            orientation='h',
            size=(30, 10)
        )
        self.silense_sl = sg.Slider(
            range=(-60, 0),
            resolution=.001,
            key=self.ns + 'silence_treshold',
            tooltip='threshold in dB to count as silence',
            # enable_events=True,
            default_value=silence_def,
            orientation='h',
            size=(30, 10)
        )
        self.rel_fade_out = widgets.FadeRegions(self.ns, 'release')
        self.name = 'Trem'
        self.layout = [
            [
                self.sus_bt,
                sg.Column([[self.sus_want_cut], [self.sus_marker]]),
                self.dyn,
                self.sul,
                self.rel_bt,
                sg.Column([[self.rel_reg_bt], [self.release_region_want_cut]]),
            ],
            [
                sg.Column([[self.sus_silense_sl], [self.silense_sl]]),
                self.rel_fade_out.layout,
            ]
        ]

    @rpr.inside_reaper()
    def read(self, event: str, values: ValuesFilledType,
             tokens: ty.List[str]) -> ty.Optional[ty.List[RegionContents]]:
        wildcards: WildcardDict = {}
        if wildcard_in_tokens(tokens, Wildcard.articulation):
            wildcards[Wildcard.articulation] = 'trem'
        if wildcard_in_tokens(tokens, Wildcard.dyn):
            wildcards[Wildcard.dyn] = values[self.ns + 'dyn']
        if wildcard_in_tokens(tokens, Wildcard.sul):  # type:ignore
            wildcards[Wildcard.sul] = values[self.ns + 'sul']  # type:ignore

        # small GUI interactions

        # big funcs
        try:
            if event == self.ns + 'sus':
                rpr.Project().begin_undo_block()
                return [self.mark_sus(values, tokens, wildcards)]
            if event == self.ns + 'release_cut':
                with rpr.undo_block('cut release', flags=-1):
                    self.release_cut(
                        db_to_amplitude(
                            ty.cast(
                                float, values[self.ns + 'silence_treshold']
                            )
                        ),
                        ty.cast(str, values[self.ns + 'rel_fade_out_shape']),
                        ty.cast(float, values[self.ns + 'rel_fade_out_time'])
                    )
                return None
            if event == self.ns + 'release_region':
                rel_reg = self.make_release_region(
                    values, wildcards, tokens,
                    ty.cast(bool, values[self.ns + 'release_region_want_cut'])
                )
                return [rel_reg] if rel_reg is not None else None

            if event == self.rel_fade_out.key:
                self.fade_out_all_releases(values)
        except ItemsError as e:
            raise ArtError(e)

        return None

    def make_release_region(
        self, values: ValuesFilledType, wildcards: WildcardDict,
        tokens: ty.List[str], want_cut: bool
    ) -> ty.Optional[RegionContents]:
        rpr.Project().begin_undo_block()
        if want_cut:
            retval = self.release_cut(
                db_to_amplitude(
                    ty.cast(float, values[self.ns + 'silence_treshold'])
                ), ty.cast(str, values[self.ns + 'rel_fade_out_shape']),
                ty.cast(float, values[self.ns + 'rel_fade_out_time'])
            )
            if not retval:
                return None
            else:
                cut_handler, median = retval
        else:
            cut_handler = ItemsHandler()
            ret_meta = self.get_metadata_safe('left')
            if ret_meta is None:
                return None
            reg, metadata = ret_meta
            median = ty.cast(float, metadata['median_rms'])
        wildcards.update(self.process_wildcards(tokens))
        if wildcard_in_tokens(tokens, Wildcard.part):
            wildcards[Wildcard.part] = 'rls'
        root = self.get_root(wildcards, cut_handler)
        metadata = {
            'part': 'release',
            'root': root,
            'median_rms': float(median)
        }
        return (
            wildcards, *cut_handler.get_bounds(count_ts=False),
            'trem release region', metadata
        )

    def fade_out_all_releases(
        self,
        values: ValuesFilledType,
    ) -> None:
        rls_regs = filter(
            lambda retval: retval[1]['part'] == 'release',
            self.get_all_regions()
        )
        self.rel_fade_out.fade_all(values, rls_regs)

    def get_metadata_safe(
        self, direction: str
    ) -> ty.Optional[ty.Tuple[rpr.Region, ty.Dict[str, object]]]:
        retval = self.get_closest_region('left')
        if retval:
            reg, metadata = ty.cast(
                ty.Tuple[rpr.Region, ty.Dict[str, object]], retval
            )
        if not retval or 'median_rms' not in metadata:
            proceed = sg.PopupOKCancel(
                '''\
                Cannot find previous Trem region with sus metadata.
                If proceed release cut now, it won't be connected to the median
                sus rms, which helps to mix sus and release.

                Really proceed?
                '''
            )
            if proceed == 'Cancel':
                print('canceled')
                return None
            raise ArtError('Apparently, this use-case is not implemented')
        return reg, metadata

    def release_cut(
        self, silence_level: float, fade_out_shape: str, fade_out_time: float
    ) -> ty.Optional[ty.Tuple[ItemsHandler, float]]:
        mdata_ret = self.get_metadata_safe('left')
        if not mdata_ret:
            return None
        reg, metadata = mdata_ret
        median = ty.cast(float, metadata['median_rms'])
        ih = ItemsHandler()
        point = get_last_rms_value_ms(
            ih,
            rms_target=median,
            # want_marker='cut',
        )
        left, ih = ih.split(ih.get_bounds(count_ts=True)[0] + point)
        point = get_first_rms_value_ms(
            ih,
            silence_level,
            # want_marker='end',
            below=True,
        )
        ih, right = ih.split(ih.get_bounds(count_ts=True)[0] + point)
        ts = rpr.Project().time_selection
        if ts.start == ts.end:
            left.delete()
            right.delete()
        ih.fade_out(length=fade_out_time, shape=FADE_SHAPES[fade_out_shape])
        return ih, median

    def mark_sus(
        self, values: ValuesFilledType, tokens: ty.List[str],
        wildcards: WildcardDict
    ) -> ty.Tuple[WildcardDict, float, float, str, object]:
        ih = ItemsHandler()
        start, end = ih.get_bounds(check_for_indentity=False)
        try:
            median_rms = get_rms(ih, median=True)
            if values[self.ns + 'sus_marker']:
                want_marker: ty.Optional[str] = '@Trem_sus_hard'
                get_first_rms_value_ms(ih, median_rms, want_marker=want_marker)
            split_ih = ItemsHandler(
                item_handlers=[
                    i_h for i_h in ih.item_handlers
                    if i_h.item.position == start
                ]
            )
            if values[self.ns + 'sus_want_cut']:
                start_split = get_first_rms_value_ms(
                    split_ih,
                    db_to_amplitude(
                        ty.cast(
                            float, values[self.ns + 'sus_silence_treshold']
                        )
                    )
                )
                left, split_ih = split_ih.split(start + start_split)
                left.delete()
                start, _ = split_ih.get_bounds(check_for_indentity=False)
            if wildcard_in_tokens(tokens, Wildcard.part):
                wildcards[Wildcard.part] = 'sus'
            wildcards.update(self.process_wildcards(tokens))
        except ItemsError as e:
            raise ArtError(str(e))
        root = self.get_root(wildcards, split_ih)
        metadata = {'median_rms': median_rms, 'part': 'sus', 'root': root}
        return wildcards, start, end, 'trem sus region', metadata


class Shorts(BaseArt):

    def __init__(self) -> None:
        self.name = 'Shorts'
        self.ns = 'Shorts_'
        self.art_name = sg.Combo(
            ['pick', 'pizz'],
            default_value='pick',
            key=self.ns + 'art_name',
        )
        self.art_part = sg.Combo(
            ['sus', 'stacc'],
            default_value='sus',
            key=self.ns + 'art_part',
        )
        self.cut_btn = sg.Button(
            'cut',
            key=self.ns + 'cut',
            enable_events=True,
        )
        self.region_btn = sg.Button('make regions', key=self.ns + 'regions')
        self.erase_mdata_btn = sg.Button(
            'erase part metadata', key=self.ns + 'erase_mdata'
        )
        self.pre_silence = widgets.NamedSlider(
            'pre silence',
            range=(-60, 0),
            resolution=.001,
            key=self.ns + 'pre_silence',
            tooltip='threshold in dB to count as silence before onset',
            # enable_events=True,
            default_value=-30,
            orientation='h',
            size=(30, 10)
        )
        self.pre_onset_time = widgets.NamedSlider(
            'max length before onset',
            range=(0, 1),
            resolution=.001,
            key=self.ns + 'pre_onset_time',
            tooltip='how long in sec can be attack',
            # enable_events=True,
            default_value=.15,
            orientation='h',
            size=(30, 10)
        )
        self.dyn = sg.Combo(
            values=['ff', 'f', 'p', 'pp'],
            default_value='ff',
            key=self.ns + 'dyn',
        )
        self.sul = sg.Combo(
            values=['sulTop', 'SulBot'],
            default_value='sulBot',
            key=self.ns + 'sul',
        )

        self.onset_pre_max = widgets.NamedSlider(
            'pre max time',
            range=(0, 10),
            resolution=.001,
            key=self.ns + 'onset_pre_max',
            tooltip='time in sec to seek back for peak',
            # enable_events=True,
            default_value=.4,
            orientation='h',
            size=(30, 10)
        )
        self.onset_wait = widgets.NamedSlider(
            'min sample length',
            range=(0, 10),
            resolution=.001,
            key=self.ns + 'onset_wait',
            tooltip='time in sec to skip after onset',
            # enable_events=True,
            default_value=2.5,
            orientation='h',
            size=(30, 10)
        )
        self.onset_fmin = widgets.NamedSlider(
            'bottom freq',
            range=(0, 3000),
            resolution=1,
            key=self.ns + 'onset_fmin',
            tooltip='HP filter to get parasite noises off',
            # enable_events=True,
            default_value=150,
            orientation='h',
            size=(30, 10)
        )
        self.onset_pre_avg = widgets.NamedSlider(
            'pre average time',
            need_check=True,
            range=(0, 10),
            resolution=.001,
            key=self.ns + 'onset_pre_avg',
            tooltip='time in sec to seek back for mean',
            # enable_events=True,
            default_value=.4,
            orientation='h',
            size=(20, 10)
        )
        self.onset_post_max = widgets.NamedSlider(
            'post max time',
            need_check=True,
            range=(0, 10),
            resolution=.001,
            key=self.ns + 'onset_post_max',
            tooltip='time in sec to seek forward for peak',
            # enable_events=True,
            default_value=2.5,
            orientation='h',
            size=(20, 10)
        )
        self.onset_post_avg = widgets.NamedSlider(
            'post average time',
            need_check=True,
            range=(0, 10),
            resolution=.001,
            key=self.ns + 'onset_post_avg',
            tooltip='time in sec to seek forward for mean',
            # enable_events=True,
            default_value=2.5,
            orientation='h',
            size=(20, 10)
        )
        self.onset_delta = widgets.NamedSlider(
            'delta',
            need_check=True,
            range=(0, 20),
            resolution=.001,
            key=self.ns + 'onset_delta',
            tooltip='the level above mean to be reached',
            # enable_events=True,
            default_value=1,
            orientation='h',
            size=(30, 10)
        )
        self.onset_markers = sg.Checkbox(
            'markers on onsets', default=True, key=self.ns + 'onset_marker'
        )
        self.fade_out = widgets.FadeRegions(
            self.ns, 'current type', range_=(0, 4)
        )

        main_tab = sg.Tab(
            'main',
            [
                [
                    self.art_name, self.art_part, self.dyn, self.sul,
                    self.onset_markers,
                    sg.Column(
                        [
                            [self.cut_btn, self.region_btn],
                            [self.erase_mdata_btn]
                        ]
                    )
                ],
                [self.pre_onset_time, self.onset_wait],
                [self.pre_silence, self.fade_out.layout],
            ],
        )
        onsets_tab = sg.Tab(
            'onsets detection', [
                [self.onset_pre_max],
                [self.onset_fmin, self.onset_delta],
                [self.onset_pre_avg, self.onset_post_max, self.onset_post_avg],
            ]
        )
        self.layout = [
            [
                sg.TabGroup(
                    tab_location='bottomleft', layout=[[main_tab, onsets_tab]]
                )
            ]
        ]

    @property
    def metadata_key(self) -> str:
        return (
            ty.cast(str, self.art_name.get()) +
            ty.cast(str, self.art_part.get())
        )

    @rpr.inside_reaper()
    def read(self, event: str, values: ValuesFilledType,
             tokens: ty.List[str]) -> ty.Optional[ty.List[RegionContents]]:
        wildcards: WildcardDict = {}
        if wildcard_in_tokens(tokens, Wildcard.articulation):
            wildcards[Wildcard.articulation
                      ] = ty.cast(str, values[self.ns + 'art_name'])
        if wildcard_in_tokens(tokens, Wildcard.part):
            wildcards[Wildcard.part
                      ] = ty.cast(str, values[self.ns + 'art_part'])
        if wildcard_in_tokens(tokens, Wildcard.dyn):
            wildcards[Wildcard.dyn] = values[self.ns + 'dyn']
        if wildcard_in_tokens(tokens, Wildcard.sul):  # type:ignore
            wildcards[Wildcard.sul] = values[self.ns + 'sul']  # type:ignore

        try:
            if event == self.ns + 'cut':
                self._cut(values)
                return None
            if event == self.ns + 'erase_mdata':
                self.erase_metadata()
            if event == self.fade_out.key:
                regions_w_mdata = self.regions_for_part(values)
                self.fade_out.fade_all(values, regions_w_mdata)
                return None
            if event == self.ns + 'regions':
                rpr.Project().begin_undo_block()
                return self.make_regions(values, wildcards, tokens)
        except ItemsError as e:
            raise ArtError(e)
        return None

    def make_regions(
        self, values: ValuesFilledType, wildcards: WildcardDict,
        tokens: ty.List[str]
    ) -> ty.List[RegionContents]:
        regions_w_mdata = self.regions_for_part(values)
        amount = self._get_amount_of_ready_rr(regions_w_mdata)
        handlers = ItemsHandler().split_by_items_gaps()
        export: ty.List[RegionContents] = []
        pprint(amount)
        for ih in handlers:
            wildcards_i = wildcards.copy()
            wildcards_i.update(
                self.process_wildcards(tokens, items_handler=ih)
            )
            root = self.get_root(wildcards_i, ih)
            if root not in amount:
                amount[root] = []

            rr = len(amount[root]) + 1
            if wildcard_in_tokens(tokens, Wildcard.rr):
                wildcards_i[Wildcard.rr] = rr

            metadata = {'root': root, 'part': self.metadata_key, 'rr': rr}
            pprint(metadata)
            amount[root].append(metadata)
            export.append(
                (wildcards_i, *ih.get_bounds(), 'shorts regions', metadata)
            )
        return export

    def _get_amount_of_ready_rr(
        self, regions_w_mdata: ty.Iterable[ty.Tuple[rpr.Region,
                                                    ty.Dict[str, object]]]
    ) -> ty.Dict[str, ty.List[ty.Dict[str, object]]]:
        amount: ty.Dict[str, ty.List[ty.Dict[str, object]]] = {}
        # print('\n----\nregions with mdata:')
        for rgn_w_md in regions_w_mdata:
            key = ty.cast(str, rgn_w_md[1]['root'])
            if key in amount:
                amount[key].append(rgn_w_md[1])
            else:
                amount[key] = [rgn_w_md[1]]
            # print(key, rgn_w_md[1], rgn_w_md[0].index, rgn_w_md[0].name)
        return amount

    def regions_for_part(
        self, values: ValuesFilledType
    ) -> ty.Iterable[ty.Tuple[rpr.Region, ty.Dict[str, object]]]:
        regions_w_mdata = filter(
            lambda ret: ret[1]['part'] == self.metadata_key,
            self.get_all_regions()
        )
        return regions_w_mdata

    def _cut(self, values: ValuesFilledType) -> None:
        ih = ItemsHandler()
        onsets, wait = self._get_onsets(values, ih)
        sample_bounds = self._get_samples_bounds(ih, values, onsets, wait)
        self._split_handlers_by_bounds(sample_bounds, ih, values)

    def _split_handlers_by_bounds(
        self, sample_bounds: ty.List[ty.Tuple[float, float]], ih: ItemsHandler,
        values: ValuesFilledType
    ) -> None:
        for sample_start, sample_end in sample_bounds:
            deleted, ih = ih.split(sample_start)
            sample, ih = ih.split(sample_end)
            sample.fade_out(
                self.fade_out.time(values), shape=self.fade_out.shape(values)
            )
            deleted.delete()

    def _get_samples_bounds(
        self, ih: ItemsHandler, values: ValuesFilledType,
        onsets: ty.List[float], wait: float
    ) -> ty.List[ty.Tuple[float, float]]:
        bounds = ih.get_bounds(count_ts=True)
        pre_silence = db_to_amplitude(
            ty.cast(float, (values[self.ns + 'pre_silence']))
        )
        pre_onset_time = ty.cast(float, values[self.ns + 'pre_onset_time'])
        sample_bounds: ty.List[ty.Tuple[float, float]] = []
        for idx, onset in enumerate(onsets):
            st_ofst = onset - pre_onset_time
            sh_left = get_first_rms_value_ms(
                ih,
                pre_silence,
                start_offset=st_ofst,
                end_offset=onset,
                direction='left',
                # want_marker='@start',
                below=True,
                want_trend=True,
                hop_length_spl=256,
            )

            next_onset = (
                bounds[1] if idx >= len(onsets) - 1 else onsets[idx + 1]
            )
            last_pitch = get_first_null_f0(
                ih,
                onset,
                min_duration=wait,
                end_offset=next_onset,
                offset_units=LengthUnit.ms
            )
            sample_start = bounds[0] + onset - sh_left
            sample_end = last_pitch + bounds[0]
            sample_bounds.append((sample_start, sample_end))

            print(bounds, sample_start, sample_end)
        return sample_bounds

    def _get_onsets(self, values: ValuesFilledType,
                    ih: ItemsHandler) -> ty.Tuple[ty.List[float], float]:
        pre_max = ty.cast(float, values[self.ns + 'onset_pre_max'])
        wait = ty.cast(float, values[self.ns + 'onset_wait'])
        fmin = ty.cast(int, values[self.ns + 'onset_fmin'])
        pre_avg = (
            ty.cast(float, values[self.ns + 'onset_pre_avg'])
            if values[self.ns + 'onset_pre_avg_used'] else None
        )
        post_max = (
            ty.cast(float, values[self.ns + 'onset_post_max'])
            if values[self.ns + 'onset_post_max_used'] else None
        )
        post_avg = (
            ty.cast(float, values[self.ns + 'onset_post_avg'])
            if values[self.ns + 'onset_post_avg_used'] else None
        )
        delta = (
            ty.cast(float, values[self.ns + 'onset_delta'])
            if values[self.ns + 'onset_delta_used'] else 1.0
        )
        onsets, _, _ = detect_onsets(
            ih,
            pre_max,
            wait,
            fmin=fmin,
            pre_avg=pre_avg,
            post_max=post_max,
            post_avg=post_avg,
            delta=delta,
            onset_markers='@onset'
            if ty.cast(bool, values[self.ns + 'onset_marker']) else '',
            backtrack_markers=''
        )
        return onsets, wait
