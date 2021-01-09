import typing as ty
from abc import abstractmethod, ABC
import importlib.machinery
from pathlib import Path
import sys
import re
import aenum
import enum
from itertools import chain

import PySimpleGUI as sg
from .item_handler import ItemsHandler, ItemsError
from .loop_finder import LoopFinder, LoopSlicer, LoopError
from . import persistence
from .pitch_tracker import estimate_entire_root
from .loudness import get_rms, amplitude_to_db
import reapy as rpr
# from .tools import InsideUndoContext

GUI_KEY = 'SampleEditor'
LayoutType = ty.List[ty.List[sg.Element]]
ValuesType = ty.Optional[ty.Union[ty.Dict[str, object], ty.List[object]]]
SerializationType = ty.Dict[str, ty.Union[str, int, float]]


class GuiMember(ABC):
    """Basic type for Gui rows.

    Each class instance is appended to the Gui as row.

    Members
    -------
    layout: LayoutType
        Should consist of all GUI elements of the class
    read(self, event: str, values: ValuesType) -> None:
    """

    layout: LayoutType

    @abstractmethod
    def read(self, event: str, values: ValuesType) -> ty.Optional[Exception]:
        """Abstract method to be called in event loop.

        Parameters
        ----------
        event : str
            SimpleGui event.
            It's better to have some sort of namespace for class events.
        values : ValuesType

        Returns
        -------
        Optional[Exception]
            if something should be poped up to user
        """
        ...


class LoopSlicerGui(GuiMember):

    def __init__(self) -> None:
        self.layout = []
        self.key_ns = 'LoopSlicer_'
        self.samplerate = sg.Spin(
            [4000, 8000, 11025, 22050, 44100, 12000, 24000, 48000],
            initial_value=22050,
            enable_events=True,
            key=self.key_ns + 'samplerate',
            tooltip='samplerate (ресемплинг для поиска)'
        )
        self.corr_wind = sg.Slider(
            range=(0.05, 3),
            default_value=0.35,
            resolution=0.0001,
            orientation='horizontal',
            tooltip=(
                'окно корреляции (насколько большая'
                ' часть обеих сторон должна быть похожа друг на друга)'
            ),
            key=self.key_ns + 'corr_wind'
        )
        self.slide_wind = sg.Slider(
            range=(0.1, 3),
            default_value=.7,
            resolution=0.0001,
            orientation='horizontal',
            tooltip=(
                'окно поиска лупа (насколько далеко'
                ' с обеих концов искать луп)'
            ),
            key=self.key_ns + 'slide_wind'
        )
        self.cross_length = sg.Slider(
            range=(0.0001, 1),
            default_value=0.08,
            resolution=0.0001,
            orientation='horizontal',
            tooltip='длина кроссфейда',
            key=self.key_ns + 'cross_length'
        )
        self.corr_max_treshold = sg.Slider(
            range=(0.8, 1),
            default_value=0.985,
            resolution=0.001,
            orientation='horizontal',
            tooltip='порог корреляции, после которого прекращается поиск',
            key=self.key_ns + 'corr_max_treshold'
        )
        self.corr_min_treshold = sg.Slider(
            range=(0.3, 0.96),
            default_value=0.9,
            resolution=0.001,
            orientation='horizontal',
            tooltip='порог корреляции, ниже которого вылетает ошибка',
            key=self.key_ns + 'corr_min_treshold'
        )
        self.cross_shapes = {
            'flat': 0,
            'smooth up': 1,
            'smooth down': 2,
            'har up': 3,
            'hard down': 4,
            'smooth spline': 5,
            'hard spline': 6
        }
        self.cross_shape = sg.Combo(
            list(self.cross_shapes.keys()),
            default_value='smooth up',
            key=self.key_ns + 'cross_shape',
            tooltip='форма кроссфейда',
            auto_size_text=True,
        )
        self.make_loop = sg.Button(
            'make loop', pad=((0, 0), (0, 0)), key=self.key_ns + 'make_loop'
        )
        self.frame_layout: LayoutType = [
            [self.corr_wind, self.slide_wind, self.cross_length],
            [
                self.samplerate, self.cross_shape, self.corr_min_treshold,
                self.corr_max_treshold, self.make_loop
            ],
        ]
        self.layout = [[sg.Frame('loop Slicer', self.frame_layout)]]

    def read(self, event: str, values: ValuesType) -> ty.Optional[Exception]:
        if not event.startswith(self.key_ns):
            return None
        if event != self.key_ns + 'make_loop':
            return None
        print(event, values)
        assert isinstance(values, ty.Dict)
        with rpr.inside_reaper():
            rpr.Project().begin_undo_block()
            try:
                ih = ItemsHandler(
                    sr=values[self.key_ns + 'samplerate']  # type:ignore
                )
                lf = LoopFinder(ih)
                st_ofst, end_ofst = lf.get_loop(
                    corr_wind_sec=values[self.key_ns +
                                         'corr_wind'],  # type:ignore
                    slide_wind_sec=values[self.key_ns +
                                          'slide_wind'],  # type:ignore
                    corr_treshold=values[self.key_ns +
                                         'corr_max_treshold'],  # type:ignore
                    corr_min_treshold=values[self.key_ns +  # type:ignore
                                             'corr_min_treshold'],
                )
            except (ItemsError, LoopError) as e:
                return e
            print(st_ofst, end_ofst)
            ls = LoopSlicer(ih, lf)
            ls.cut_and_fade(
                st_ofst,
                end_ofst,
                crs_length=values[self.key_ns + 'cross_length'],  # type:ignore
                crs_shape=self.cross_shapes[values[self.key_ns + 'cross_shape'
                                                   ]  # type:ignore
                                            ]
            )
            rpr.Project().end_undo_block('make loop')
        return None


if ty.TYPE_CHECKING:

    class Wildcard(enum.Enum):
        root = '$root'
        peak = '$peak'
        rms = '$rms'
        median = '$median'
        instrument = '$instrument'
        articulation = '$articulation'
        part = '$part'
        dyn = '$dyn'

else:

    class Wildcard(aenum.Enum):
        root = '$root'
        peak = '$peak'
        rms = '$rms'
        median = '$median'
        instrument = '$instrument'
        articulation = '$articulation'
        part = '$part'
        dyn = '$dyn'


WildcardDict = ty.Dict[Wildcard, ty.Union[str, float]]


def has_wildcard(string: str, wildcard: Wildcard) -> bool:
    # print(f'has_wildcard({string}, {wildcard}={wildcard.value})')
    m = re.search(re.escape(wildcard.value), string)
    # if string.find(wildcard.value) != -1:
    if m:
        # print('--True')
        return True
    # print('--False')
    return False


def replace_wildcard(
    string: str, wildcard: Wildcard, repl: ty.Union[str, float]
) -> str:
    return re.sub(re.escape(wildcard.value), str(repl), string)


def check_token_for_wildcards(token: str, wildcards: WildcardDict) -> str:
    print(f'check_token_for_wildcards({token}, {wildcards})')
    for wildcard, repl in wildcards.items():
        if has_wildcard(token, wildcard):
            token = replace_wildcard(token, wildcard, repl)
            print(f'replaced: new_token={token}, {wildcard}, {repl}')
    if '$' in token:
        print(f'$ in {token}')
        return ''
    return token


def wildcard_in_tokens(tokens: ty.List[str], wildcard: Wildcard) -> bool:
    # print(f'wildcard_in_tokens({tokens}, {wildcard})')
    for token in tokens:
        if has_wildcard(token, wildcard):
            # print('--True')
            return True
    # print('--False')
    return False


class BaseArt:
    layout: LayoutType
    name: str

    @abstractmethod
    def read(
        self, event: str, values: ValuesType, region_tokens: ty.List[str]
    ) -> ty.Optional[ty.Tuple[WildcardDict, float, float, str]]:
        ...

    def process_wildcards(self, tokens: ty.List[str]) -> WildcardDict:
        ih = ItemsHandler()
        audio = ih.load_audio()
        wildcards: WildcardDict = {}
        for token in tokens:
            if has_wildcard(token, wildcard=Wildcard.root):
                root = estimate_entire_root(audio[0], ih.sr)
                wildcards.update({Wildcard.root: root})
            if has_wildcard(token, wildcard=Wildcard.peak):
                peak = amplitude_to_db(max(audio[0]))
                wildcards.update({Wildcard.peak: '{:5.2f}'.format(peak)})
            if has_wildcard(token, wildcard=Wildcard.rms):
                rms = amplitude_to_db(get_rms(ih))
                wildcards.update({Wildcard.rms: '{:5.2f}'.format(rms)})
            if has_wildcard(token, wildcard=Wildcard.median):
                median = amplitude_to_db(get_rms(ih, median=True))
                wildcards.update({Wildcard.median: '{:5.2f}'.format(median)})
        return wildcards


class ArtError(Exception):
    ...


class ArtsHandler:

    def __init__(
        self,
        tabs_layout: ty.Optional[LayoutType] = None,
        arts_instances: ty.Optional[ty.List[BaseArt]] = None
    ) -> None:
        if arts_instances is None:
            arts_instances = []
        self.arts_instances: ty.List[BaseArt] = arts_instances
        self.key_ns = 'ArtsHandler_'
        self.text_width = 50
        self.instrument_name = sg.Input(
            'Instrument',
            key=self.key_ns + 'instrument_name',
            enable_events=True,
            size=(self.text_width, 1),
            tooltip='instrument name to be used in mask'
        )
        self.region_mask = sg.Input(
            '$instrument,$articulation,$part,$dyn,$peakdB,$mediandB,$root',
            key=self.key_ns + 'region_mask',
            enable_events=True,
            size=(self.text_width, 1),
            tooltip='mask for region name. "," is separator, "$" is wildcard'
        )
        self.sep_text = sg.Text('sep', size=(3, 1))
        self.sep_input = sg.Input(
            '_', size=(3, 1), key=self.key_ns + 'sep_input'
        )
        self.arts_file = sg.Input(
            key=self.key_ns + 'arts_file',
            size=(18, 1),
            enable_events=True,
            disabled=True,
        )
        self.load_btn = sg.FileBrowse(
            'load arts',
            target=self.key_ns + 'arts_file',
            file_types=(
                ("Python Files", "*.py"),
                ("All Files", "*.*"),
            ),
            # enable_events=True,
            key=self.key_ns + 'load_arts',
            tooltip='load file with articulation classes'
        )
        self.wildcards_spin = sg.Combo(
            [wc.value for wc in Wildcard],
            key=self.key_ns + 'wildcards_spin',
            enable_events=True
        )
        if tabs_layout is None:
            self.tab_layout = [
                [
                    sg.Tab(
                        'noting here',
                        [[sg.Text('articulations are not loaded')]]
                    )
                ]
            ]
        else:
            self.tab_layout = tabs_layout
        self.frame_layout = [
            [self.instrument_name, self.arts_file, self.load_btn],
            [
                self.region_mask, self.wildcards_spin, self.sep_text,
                self.sep_input
            ],
            [sg.TabGroup(self.tab_layout)],
        ]
        self.layout = [[sg.Frame('Articulation handler', self.frame_layout)]]

    def make_region(
        self, wildcards: WildcardDict, start: float, end: float, undo_name: str
    ) -> rpr.Region:
        tokens = self.region_tokens
        if wildcard_in_tokens(tokens, Wildcard.instrument):
            wildcards.update({Wildcard.instrument: self.instrument_name.get()})
        sep = self.sep_input.get()
        contents: ty.List[str] = []
        for token in tokens:
            if result := check_token_for_wildcards(token, wildcards):
                print(f'--result: {result}')
                contents.append(result)
        region_name = sep.join(contents)
        region = rpr.Project().add_region(start, end, name=region_name)
        rpr.Project().end_undo_block(undo_name)
        return region

    @property
    def region_tokens(self) -> ty.List[str]:
        return self.region_mask.get().split(',')  # type:ignore

    def read(
        self, event: str, values: ValuesType
    ) -> ty.Optional[ty.Union[Exception, ty.Tuple[LayoutType,
                                                  ty.List[BaseArt]]]]:
        try:
            for art in self.arts_instances:
                print(
                    f'{self} ({id(self)}) is reading for {art}, event is {event}'
                )
                retval = art.read(event, values, self.region_tokens)
                print(f'retval is {retval}')
                if retval is not None:
                    self.make_region(*retval)
                    return None
        except ArtError as e:
            return e

        if event == self.key_ns + 'wildcards_spin':
            self.region_mask.Update(
                value=values[self.key_ns + 'region_mask'] +  # type:ignore
                values[self.key_ns + 'wildcards_spin']  # type:ignore
            )

        if event == self.key_ns + 'arts_file':
            path = Path(
                ty.cast(str, values[self.key_ns + 'arts_file'])  # type:ignore
            )
            if not path.is_file():
                return TypeError(f'file {path} does not exists')
            name = path.name[:-len(path.suffix)]
            loader = importlib.machinery.SourceFileLoader(name, str(path))
            module = loader.load_module(loader.name)
            loader.exec_module(module)

            classes: ty.List[ty.Type[BaseArt]] = []
            for name in dir(module):
                obj = module.__dict__[name]
                if not isinstance(obj, type):
                    continue
                if obj is BaseArt:
                    continue
                if issubclass(obj, BaseArt):
                    classes.append(obj)
            arts_instances = [cls_() for cls_ in classes]
            return [
                [sg.Tab(art.name, art.layout) for art in arts_instances]
            ], arts_instances
        return None


def _load_values(window: sg.Window) -> None:
    values = persistence.proj_loads(rpr.Project(), GUI_KEY)
    if values in (None, ''):
        return
    for key, val in values.items():  # type:ignore
        window[key].update(val)


def _make_window(
    loop_slicer: LoopSlicerGui, arts_handler: ArtsHandler, load_values: bool
) -> sg.Window:
    layout = []
    for sub_lay in (loop_slicer.layout, arts_handler.layout):
        layout.extend(sub_lay)

    window = sg.Window('Sample Editor (by Levitanus)', layout)
    window.Finalize()
    if load_values:
        _load_values(window)
    return window


def run(load_values: bool = True) -> None:
    """Main gui function, used to launch script.

    Parameters
    ----------
    load_values : bool, optional
        If loading of persistent values is needed.
    """
    ls = LoopSlicerGui()
    ah = ArtsHandler()
    window = _make_window(ls, ah, load_values)

    def check_for_exception(result: ty.Optional[Exception]) -> None:
        if result is None:
            return
        sg.popup_error(str(result))

    serialized = None
    while True:
        event, values = ty.cast(ty.Tuple[str, ValuesType], window.read())
        if event == sg.WIN_CLOSED:
            # values = values
            break
        serialized = values

        check_for_exception(ls.read(event, values))
        ah_read_ret = ah.read(event, values)
        if isinstance(ah_read_ret,
                      tuple) and isinstance(ah_read_ret[0], ty.List):
            ah = ArtsHandler(
                tabs_layout=ah_read_ret[0], arts_instances=ah_read_ret[1]
            )
            ls = LoopSlicerGui()
            if serialized is not None:
                persistence.proj_dumps(rpr.Project(), GUI_KEY, serialized)
            wind1 = _make_window(ls, ah, load_values)
            window.close()
            window = wind1
        else:
            ah.read(event, values)
            # check_for_exception(ah.read(event, values))  # typeLignore
    if serialized is not None:
        persistence.proj_dumps(rpr.Project(), GUI_KEY, serialized)
    window.close()
