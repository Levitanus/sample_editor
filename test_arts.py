import typing as ty
import PySimpleGUI as sg
from aenum import extend_enum
import reapy as rpr

from sample_editor.item_handler import ItemsHandler, ItemHandler, ItemsError
from sample_editor.gui import (
    BaseArt, ValuesType, Wildcard, WildcardDict, wildcard_in_tokens, ArtError,
    REGION_KEY, FADE_SHAPES
)
from sample_editor.loudness import (
    get_rms, get_first_rms_value_ms, get_last_rms_value_ms, amplitude_to_db,
    db_to_amplitude
)
from sample_editor.pitch_tracker import estimate_entire_root

for name, value in (('sul', '$sul'), ):
    extend_enum(Wildcard, name, value)


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
        self.fade_out_sl = sg.Slider(
            range=(0, 1),
            resolution=.001,
            key=self.ns + 'rel_fade_out_time',
            tooltip='release fade-out time',
            # enable_events=True,
            default_value=.2,
            orientation='h',
            size=(30, 10)
        )
        self.rel_fade_out_sh = sg.Combo(
            values=list(FADE_SHAPES.keys()),
            default_value=list(FADE_SHAPES.keys())[1],
            key=self.ns + 'rel_fade_out_shape',
            tooltip='release fade-out shape'
        )
        self.rel_make_fades_btn = sg.Button(
            'make all fadeouts', key=self.ns + 'make_release_fades'
        )
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
                sg.Column(
                    [
                        [self.fade_out_sl],
                        [self.rel_fade_out_sh, self.rel_make_fades_btn]
                    ]
                ),
            ]
        ]

    @rpr.inside_reaper()
    def read(
        self, event: str, values: ValuesType, tokens: ty.List[str]
    ) -> ty.Optional[ty.Tuple[WildcardDict, float, float, str, object]]:
        wildcards: WildcardDict = {}
        if wildcard_in_tokens(tokens, Wildcard.articulation):
            wildcards[Wildcard.articulation] = 'trem'
        if wildcard_in_tokens(tokens, Wildcard.dyn):
            wildcards[Wildcard.dyn] = values[self.ns + 'dyn']  # type:ignore
        if wildcard_in_tokens(tokens, Wildcard.sul):
            wildcards[Wildcard.sul] = values[self.ns + 'sul']  # type:ignore

        # small GUI interactions

        # big funcs
        try:
            if event == self.ns + 'sus':
                rpr.Project().begin_undo_block()
                return self.mark_sus(values, tokens, wildcards)
            if event == self.ns + 'release_cut':
                with rpr.undo_block('cut release', flags=-1):
                    self.release_cut(
                        db_to_amplitude(values[self.ns + 'silence_treshold']),
                        values[self.ns + 'rel_fade_out_shape'],
                        values[self.ns + 'rel_fade_out_time']
                    )
                return None
            if event == self.ns + 'release_region':
                return self.make_release_region(
                    values, wildcards, tokens,
                    values[self.ns + 'release_region_want_cut']
                )
            if event == self.ns + 'make_release_fades':
                self.fade_out_all_releases(values)
        except ItemsError as e:
            raise ArtError(e)

        return None

    def make_release_region(
        self, values: ValuesType, wildcards: WildcardDict,
        tokens: ty.List[str], want_cut: bool
    ) -> ty.Optional[ty.Tuple[WildcardDict, float, float, str, object]]:
        rpr.Project().begin_undo_block()
        if want_cut:
            retval = self.release_cut(
                db_to_amplitude(values[self.ns + 'silence_treshold']),
                values[self.ns + 'rel_fade_out_shape'],
                values[self.ns + 'rel_fade_out_time']
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
            median = metadata['median_rms']
        wildcards.update(self.process_wildcards(tokens))
        if wildcard_in_tokens(tokens, Wildcard.part):
            wildcards[Wildcard.part] = 'rls'
        root = self.get_root(wildcards, cut_handler)
        metadata = {'part': 'release', 'root': root, 'median_rms': median}
        return (
            wildcards, *cut_handler.get_bounds(count_ts=False),
            'trem release region', metadata
        )

    def fade_out_all_releases(
        self,
        values: ValuesType,
    ) -> None:
        with rpr.undo_block(
            'set all releases fade-outs to {time}'.format(
                time=values[self.ns + 'rel_fade_out_time']
            ), -1
        ):
            with rpr.inside_reaper():
                rls_regs = filter(
                    lambda retval: retval[1]['part'] == 'release',
                    self.get_all_regions()
                )
                pr = rpr.Project()
                for rls_tuple in rls_regs:
                    reg, metadata = rls_tuple
                    for item in pr.items:
                        if (
                            item.position >= reg.start and
                            item.position + item.length <= reg.end
                        ):
                            item.is_selected = True
                        else:
                            item.is_selected = False

                    ih = ItemsHandler()
                    ih.fade_out(
                        values[self.ns + 'rel_fade_out_time'],
                        FADE_SHAPES[values[self.ns + 'rel_fade_out_shape']],
                    )

    def get_root(
        self, wildcards: WildcardDict, items_handler: ItemsHandler
    ) -> str:
        if Wildcard.root not in wildcards:
            root = estimate_entire_root(
                items_handler.load_audio()[0], sr=items_handler.sr
            )
        else:
            root = ty.cast(str, wildcards[Wildcard.root])
        return root

    def get_metadata_safe(
        self, direction: str
    ) -> ty.Optional[ty.Tuple[rpr.Region, ty.Dict[str, object]]]:
        retval = self.get_closest_region('left')
        if retval:
            reg, metadata = retval
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
        return reg, metadata  # type:ignore

    def release_cut(
        self, silence_level: float, fade_out_shape: str, fade_out_time: float
    ) -> ty.Optional[ty.Tuple[ItemsHandler, float]]:
        reg, metadata = self.get_metadata_safe('left')
        median = metadata['median_rms']
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
        self, values: ValuesType, tokens: ty.List[str], wildcards: WildcardDict
    ) -> ty.Tuple[WildcardDict, float, float, str, object]:
        ih = ItemsHandler()
        start, end = ih.get_bounds(check_for_indentity=False)
        try:
            median_rms = get_rms(ih, median=True)
            if values[self.ns + 'sus_marker']:  # type:ignore
                want_marker: ty.Optional[str] = '@Trem_sus_hard'
                get_first_rms_value_ms(ih, median_rms, want_marker=want_marker)
            split_ih = ItemsHandler(
                item_handlers=[
                    i_h for i_h in ih.item_handlers
                    if i_h.item.position == start
                ]
            )
            if values[self.ns + 'sus_want_cut']:  # type:ignore
                start_split = get_first_rms_value_ms(
                    split_ih,
                    db_to_amplitude(values[self.ns + 'sus_silence_treshold'])
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
