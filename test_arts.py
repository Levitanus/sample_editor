import typing as ty
import PySimpleGUI as sg
from aenum import extend_enum
import reapy as rpr

from sample_editor.item_handler import ItemsHandler, ItemsError
from sample_editor.gui import (
    BaseArt, ValuesType, Wildcard, WildcardDict, wildcard_in_tokens, ArtError
)
from sample_editor.loudness import (
    get_rms, get_first_rms_value_ms, get_last_rms_value_ms
)

# for name, value in (('dynmusical', '$dynmusical'), ):
#     extend_enum(Wildcard, name, value)


class Trem(BaseArt):

    def __init__(self) -> None:
        self.ns = 'Trem_'
        self.sus_bt = sg.Button('sus region', key=self.ns + 'sus')
        self.sus_marker = sg.Check(
            'marker on hard attack', default=True, key=self.ns + 'sus_marker'
        )
        self.rel_bt = sg.Button('cut release', key=self.ns + 'release_cut')
        self.rel_reg_bt = sg.Button(
            'release region', key=self.ns + 'release_region'
        )
        self.dyn = sg.Combo(
            values=['ff', 'f', 'p', 'pp'],
            default_value='ff',
            key=self.ns + 'dyn',
        )
        self.name = 'Trem'
        self.layout = [
            [
                self.sus_bt,
                self.sus_marker,
                self.rel_bt,
                self.rel_reg_bt,
                self.dyn,
            ]
        ]

    @rpr.inside_reaper()
    def read(
        self, event: str, values: ValuesType, tokens: ty.List[str]
    ) -> ty.Optional[ty.Tuple[WildcardDict, float, float, str]]:
        wildcards: WildcardDict = {}
        if wildcard_in_tokens(tokens, Wildcard.articulation):
            wildcards[Wildcard.articulation] = 'trem'
        if wildcard_in_tokens(tokens, Wildcard.dyn):
            wildcards[Wildcard.dyn] = values[self.ns + 'dyn']  # type:ignore
        if event == self.ns + 'sus':
            rpr.Project().begin_undo_block()
            ih = ItemsHandler()
            start, end = ih.get_bounds(check_for_indentity=False)
            try:
                if values[self.ns + 'sus_marker']:  # type:ignore
                    want_marker: ty.Optional[str] = '@Trem_sus_hard'
                    median_rms = get_rms(ih, median=True)
                    get_first_rms_value_ms(
                        ih, median_rms, want_marker=want_marker
                    )
                else:
                    want_marker = None
                if wildcard_in_tokens(tokens, Wildcard.part):
                    wildcards[Wildcard.part] = 'sus'
                wildcards.update(self.process_wildcards(tokens))
            except ItemsError as e:
                raise ArtError(str(e))
            print(f'returning {wildcards}, {start}, {end}, trem sus region')
            return wildcards, start, end, 'trem sus region'
        return None
