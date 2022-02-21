import typing as ty
import PySimpleGUI as sg
import reapy_boost as rpr
from pprint import pprint

from .gui import (LayoutType, FADE_SHAPES, ValuesFilledType)
from .item_handler import (ItemsHandler, ItemHandler)


def NamedSlider(
    name: str,
    range: ty.Tuple[float, float],
    key: str,
    need_check: bool = False,
    resolution: float = .001,
    tooltip: str = '',
    enable_events: bool = False,
    default_value: ty.Optional[float] = None,
    orientation: str = 'h',
    size: ty.Tuple[int, int] = (30, 10)
) -> sg.Column:
    text_layout = [sg.Text(name)]
    if need_check:
        text_layout.append(
            sg.Checkbox('use', key=key + '_used', default=False)
        )
    return sg.Column(
        [
            text_layout,
            [
                sg.Slider(
                    range,
                    key=key,
                    resolution=resolution,
                    tooltip=tooltip,
                    enable_events=enable_events,
                    default_value=default_value,
                    orientation=orientation,
                    size=size
                )
            ],
        ]
    )


class FadeRegions:
    layout: LayoutType

    def __init__(
        self,
        namespace: str,
        name: str,
        direction: str = 'fade_out',
        range_: ty.Tuple[float, float] = (0, 1)
    ) -> None:
        self.name = name
        self.sr = 8000

        assert direction in (
            'fade_out', 'fade_in'
        ), 'direction can be only "fade_out" or "fade_in"'
        self.direction_text = (
            'fade-out' if direction == 'fade_out' else 'fade-in'
        )

        self.ns = namespace + f'{direction}_'
        self.fade_sl = NamedSlider(
            f'{self.direction_text} time',
            range_,
            key=self.ns + 'fade_time',
            resolution=.001,
            tooltip=f'{name} {self.direction_text} time',
            default_value=.2,
            orientation='h',
            size=(30, 10)
        )
        self.fade_sh = sg.Combo(
            values=list(FADE_SHAPES.keys()),
            default_value=list(FADE_SHAPES.keys())[1],
            key=self.ns + 'fade_shape',
            tooltip=f'{self.name} {self.direction_text} shape'
        )
        self.make_fades_btn = sg.Button(
            f'make all {self.direction_text}s', key=self.ns + 'make_fades'
        )
        self.layout = sg.Column(
            [[self.fade_sl], [self.fade_sh, self.make_fades_btn]]
        )

    @property
    def key(self) -> str:
        return self.ns + 'make_fades'

    def time(self, values: ValuesFilledType) -> float:
        return ty.cast(float, values[self.ns + 'fade_time'])

    def shape(self, values: ValuesFilledType) -> int:
        return FADE_SHAPES[ty.cast(str, values[self.ns + 'fade_shape'])]

    def fade_all(
        self, values: ValuesFilledType,
        regions_w_metadata: ty.Iterable[ty.Tuple[rpr.Region, object]]
    ) -> None:
        with rpr.undo_block(
            'set all {name}s {d_t}s to {time}'.format(
                name=self.name,
                d_t=self.direction_text,
                time=values[self.ns + 'fade_time']
            ), -1
        ):
            print('fade_all')
            pr = rpr.Project()
            pr.select_all_items(False)
            all_items: ty.Iterator[rpr.Item] = pr.items  # type:ignore
            for_fade: ty.Iterator[rpr.Item] = []  # type:ignore

            def is_in_bounds(
                item_bounds: ty.Tuple[float, float],
                region_bounds: ty.Tuple[float, float]
            ) -> bool:
                # print(item_bounds, region_bounds)
                if (
                    item_bounds[0] >= region_bounds[0] and
                    item_bounds[1] <= region_bounds[1]
                ):
                    return True
                return False

            def item_for_selection(
                item: rpr.Item, regions_bounds: ty.Iterable[ty.Tuple[float,
                                                                     float]]
            ) -> bool:
                start = item.position
                end = start + item.length
                if len(
                    list(
                        filter(
                            lambda r_b: is_in_bounds((start, end), r_b),
                            regions_bounds
                        )
                    )
                ):
                    return True
                return False

            regions_w_metadata = list(regions_w_metadata)
            pprint(list(reg[0].name for reg in regions_w_metadata))

            regs_bounds = list(
                [(reg[0].start, reg[0].end) for reg in regions_w_metadata]
            )
            for_fade = filter(
                lambda item: item_for_selection(item, regs_bounds), all_items
            )

            handlers = [
                ItemHandler(sr=self.sr, item=item) for item in for_fade
            ]
            print(list(handl.item.position for handl in handlers))
            ih = ItemsHandler(sr=self.sr, item_handlers=handlers)
            ih.fade_out(
                ty.cast(float, values[self.ns + 'fade_time']),
                FADE_SHAPES[ty.cast(str, values[self.ns + 'fade_shape'])],
            )
