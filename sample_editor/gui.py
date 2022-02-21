import typing as ty
from abc import abstractmethod, ABC
import importlib.machinery
from pathlib import Path
import re
import aenum
import enum
from warnings import warn
import pickle
from pprint import pprint

import PySimpleGUI as sg
from .item_handler import ItemsHandler, ItemsError
from .loop_finder import LoopFinder, LoopSlicer, LoopError
from .pitch_tracker import estimate_entire_root
from .loudness import get_rms, amplitude_to_db
import reapy_boost as rpr

GUI_SECTION = 'SampleEditor'
GUI_KEY = 'CONTROL_VALUES'
REGION_KEY = 'region_meta'
LayoutType = ty.List[ty.List[sg.Element]]
ValuesFilledType = ty.Dict[str, ty.Union[str, float, bool]]
ValuesType = ty.Optional[ValuesFilledType]
# SerializationType = ty.Dict[str, ty.Union[str, int, float]]
FADE_SHAPES = {
    'flat': 0,
    'smooth up': 1,
    'smooth down': 2,
    'har up': 3,
    'hard down': 4,
    'smooth spline': 5,
    'hard spline': 6
}


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
    """Internal Gui class used for make LoopSlicer section."""

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
        self.cross_shapes = FADE_SHAPES
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
        rr = '$rr'

else:

    class Wildcard(aenum.Enum):
        """Used for manipulating of region mask wildcards.

        Attributes
        ----------
        articulation : str
        dyn : str
        instrument : str
        median : str
        part : str
        peak : str
        rms : str
        root : str

        See Also
        --------
        has_wildcard()
        replace_wildcard()
        check_token_for_wildcards()
        wildcard_in_tokens()
        """

        root = '$root'
        peak = '$peak'
        rms = '$rms'
        median = '$median'
        instrument = '$instrument'
        articulation = '$articulation'
        part = '$part'
        dyn = '$dyn'
        rr = '$rr'


WildcardDict = ty.Dict[Wildcard, ty.Union[str, float]]


def has_wildcard(string: str, wildcard: Wildcard) -> bool:
    """Check whether string contains wildcard.

    Parameters
    ----------
    string : str
    wildcard : Wildcard

    Returns
    -------
    bool
    """
    m = re.search(re.escape(wildcard.value), string)
    if m:
        return True
    return False


def replace_wildcard(
    string: str, wildcard: Wildcard, repl: ty.Union[str, float]
) -> str:
    """Replace wildcard with string.

    Parameters
    ----------
    string : str
    wildcard : Wildcard
    repl : ty.Union[str, float]
    """
    return re.sub(re.escape(wildcard.value), str(repl), string)  # type:ignore


def check_token_for_wildcards(token: str, wildcards: WildcardDict) -> str:
    """Check if token contains one of wildcards.

    Parameters
    ----------
    token : str
    wildcards : WildcardDict
        {Wildcard.mamber:replace_string}

    Returns
    -------
    str
        token with replaced wildcards.

    Note
    ----
    If even one wildcard for token is missing — token will be omited.
    """
    for wildcard, repl in wildcards.items():
        if has_wildcard(token, wildcard):
            token = replace_wildcard(token, wildcard, repl)
    if '$' in token:
        return ''
    return token


def wildcard_in_tokens(tokens: ty.List[str], wildcard: Wildcard) -> bool:
    """Check whether particular wildcard presents in tokens.

    Parameters
    ----------
    tokens : ty.List[str]
    wildcard : Wildcard

    Returns
    -------
    bool
    """
    for token in tokens:
        if has_wildcard(token, wildcard):
            return True
    return False


RegionContents = ty.Tuple[WildcardDict, float, float, str, object]


class BaseArt:
    """Base class to use for making articulation slicing tools.

     __init__ method has to define:
        * articulation GUI layout in `self.layout`
        * articulation name in `self.name`

    read(
        self, event: str, values: ValuesType, region_tokens: ty.List[str]
    ) -> ty.Optional[ty.Tuple[WildcardDict, float, float, str, object]]:
        is the main method for interaction with GUI.

        * it can do any thing You wish, but if making of region is needed
            method should return tuple:
            (processed wildcards, region start, region end, region name,
            region metadata)
        * This method has to invoke `self.process_wildcards(tokens)`
            for each returning region. It is the matter of choice —
            when to invoke it: but for avoiding of unnecessary calculations
            is better to call it right after preparing the region:
            `wildcards.update(self.process_wildcards(tokens))`
        * Any Exception raised inside this method will crash the GUI.
            You should raise ArtError to display the error text in popup.

    See `articulations_example.py` for inspiration.
    """

    layout: LayoutType
    name: str

    @abstractmethod
    def read(
        self, event: str, values: ValuesFilledType, region_tokens: ty.List[str]
    ) -> ty.Optional[ty.List[RegionContents]]:
        ...

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

    def process_wildcards(
        self,
        tokens: ty.List[str],
        items_handler: ty.Optional[ItemsHandler] = None
    ) -> WildcardDict:
        """Get WildcardDict for requested tokens.

        Parameters
        ----------
        tokens : ty.List[str]

        Returns
        -------
        WildcardDict
            Calculates only necessary features for tokens.
        """
        ih = ItemsHandler() if items_handler is None else items_handler
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

    def get_closest_region(
        self, direction: str
    ) -> ty.Optional[ty.Tuple[rpr.Region, object]]:
        """Find closest Region with articulation metadata.

        Parameters
        ----------
        direction : str
            'left' or 'right'

        Returns
        -------
        Optional[Tuple[reapy.Region, object]]
            region and metadata if any
        """
        pr = rpr.Project()
        assert direction in (
            'left', 'right'
        ), "direction can be only 'left' or 'right'"
        if direction == 'left':
            start = .0
        else:
            start = pr.length
        closest: ty.Optional[ty.Tuple[rpr.Region, object]] = None
        for reg in pr.regions:
            key = f'{REGION_KEY}_{reg.index}_{self.name}'
            if metadata := pr.get_ext_state(GUI_SECTION, key, pickled=True):
                if (
                    direction == 'left' and
                    pr.cursor_position > reg.start > start
                ):
                    start = reg.start
                    closest = reg, metadata
                    continue
                if (
                    direction == 'right' and
                    pr.cursor_position < reg.start < start
                ):
                    start = reg.start
                    closest = reg, metadata
                    continue
        if closest is not None:
            return closest

        return None

    def _all_regions_with_keys(
        self
    ) -> ty.Tuple[ty.List[rpr.Region], ty.Iterable[str]]:
        pr = rpr.Project()
        regions = list(pr.regions)
        keys = [f'{REGION_KEY}_{reg.index}_{self.name}' for reg in regions]
        return regions, keys

    def erase_metadata(self) -> None:
        with rpr.inside_reaper():
            regions, keys = self._all_regions_with_keys()
            keys = list(keys)
            pprint(('erasing metadata for keys:', keys))
            rpr.Project().map(
                'set_ext_state', {'key': keys},
                defaults={
                    'section': GUI_SECTION,
                    'pickled': False,
                    'value': '',
                }
            )

    def get_all_regions(
        self
    ) -> ty.List[ty.Tuple[rpr.Region, ty.Dict[str, object]]]:
        """Get all regions with articulation metadata.

        Returns
        -------
        List[Tuple[reapy.Region, Dict[str, object]]]
        """
        retvals: ty.List[ty.Tuple[rpr.Region, ty.Dict[str, object]]] = []
        with rpr.inside_reaper():
            regions, keys = self._all_regions_with_keys()
            metadatas = pickle.loads(
                rpr.Project().map(
                    'get_ext_state', {
                        'key': keys
                    },
                    defaults={
                        'section': GUI_SECTION,
                        'pickled': True
                    },
                    pickled_out=True
                ).encode('latin-1')
            )
            for reg, metadata in zip(regions, metadatas):
                if metadata:
                    retvals.append((reg, metadata))
        pprint(retvals)
        return retvals


class ArtError(Exception):
    """Special exception to be raised inside BaseArt.read() method."""


class ArtsHandler:
    """Big scary class making the main GUI work for articulations section.

    Attributes
    ----------
    arts_file : Input
        file with articulation classes
    frame_layout : LayoutType
    instrument_name : Input
    key_ns : str
        widgets key namespace
    layout : LayoutType
    load_btn : FileBrowse
        to load articulations
    region_mask : Input
        for organizing region name
    rendered_tracks_button : Button
        to mark rendered tracks
    rendered_tracks_text : Input
        to keep rendered tracks GUID
    sep_input : Inout
        To request tokens separator
    sep_text : Text
    tabs_layout : LayoutType
        used as parameter if articulations loaded
    text_width : int
        articulations section text fields width
    wildcards_spin : Spin
    """

    def __init__(
        self,
        tabs_layout: ty.Optional[LayoutType] = None,
        arts_instances: ty.Optional[ty.List[BaseArt]] = None
    ) -> None:
        """
        Parameters
        ----------
        tabs_layout : Optional[LayoutType], optional
            If articulations layout is ready
        arts_instances : Optional[List[BaseArt]], optional
            If Articulations are loaded
        """
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
            '$instrument,$articulation,$part,$dyn,$rr,$root',
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
            size=(15, 1),
            key=self.key_ns + 'wildcards_spin',
            enable_events=True
        )
        self.rendered_tracks_text = sg.Input(
            'master',
            disabled=True,
            size=(self.text_width + 20, 1),
            key=self.key_ns + 'rendered_tracks_text',
            tooltip='select tracks for adding in render matrix. '
            'Master by default'
        )
        self.rendered_tracks_button = sg.Button(
            'set tracks',
            key=self.key_ns + 'rendered_tracks_button',
            enable_events=True,
            tooltip='select tracks and press. '
            'if no track selected — master will be used.'
        )
        if tabs_layout is None:
            self.tabs_layout = [
                [
                    sg.Tab(
                        'noting here',
                        [[sg.Text('articulations are not loaded')]]
                    )
                ]
            ]
        else:
            self.tabs_layout = tabs_layout
        self.frame_layout = [
            [self.rendered_tracks_text, self.rendered_tracks_button],
            [self.instrument_name, self.arts_file, self.load_btn],
            [
                self.region_mask, self.wildcards_spin, self.sep_text,
                self.sep_input
            ],
            [sg.TabGroup(self.tabs_layout)],
        ]
        self.layout = [[sg.Frame('Articulation handler', self.frame_layout)]]

    def make_region(
        self, wildcards: WildcardDict, start: float, end: float,
        undo_name: str, metadata: object, art: BaseArt
    ) -> rpr.Region:
        """Make region and save metadata in project.

        Note
        ----
        called in read() method if articulation returned region data.

        Parameters
        ----------
        wildcards : WildcardDict
        start : float
        end : float
        undo_name : str
        metadata : object
            any metadata to be stored inside project for current region index.
        """
        tokens = self.region_tokens
        if wildcard_in_tokens(tokens, Wildcard.instrument):
            wildcards.update({Wildcard.instrument: self.instrument_name.get()})
        sep = self.sep_input.get()
        contents: ty.List[str] = []
        for token_ in tokens:
            if result_ := check_token_for_wildcards(token_, wildcards):
                contents.append(result_)
        region_name = sep.join(contents)
        region = rpr.Project().add_region(start, end, name=region_name)
        if self.rendered_tracks_text.get() == 'master':
            tracks = [rpr.Project().master_track]
        else:
            tracks = [
                rpr.Track.from_GUID(guid)
                for guid in self.rendered_tracks_text.get().split(',')
            ]
        region.add_rendered_tracks(tracks)
        key = f'{REGION_KEY}_{region.index}_{art.name}'
        print(key, region.start, region.enum_index, region_name)
        rpr.Project().set_ext_state(GUI_SECTION, key, metadata, pickled=True)
        # # toggle repeat
        # rpr.perform_action(1068)
        # rpr.perform_action(1068)
        # rpr.update_timeline()
        # rpr.Project().end_undo_block(undo_name)
        return region

    @property
    def region_tokens(self) -> ty.List[str]:
        """Region name mask, split by tokens.

        :type: List[str]
        """
        return self.region_mask.get().split(',')  # type:ignore

    def read(
        self, event: str, values: ValuesType
    ) -> ty.Optional[ty.Union[Exception, ty.Tuple[LayoutType,
                                                  ty.List[BaseArt]]]]:
        # check if arts can do something with event and need for region
        try:
            for art in self.arts_instances:
                if not isinstance(values, ty.Dict):
                    raise TypeError(f'values are of bad type: {type(values)}')
                retval = art.read(event, values, self.region_tokens)
                if retval is not None:
                    for contents in retval:
                        self.make_region(*contents, art)
                        undo_name = contents[3]
                    rpr.Project().end_undo_block(undo_name)
                    return None
        except ArtError as e:
            return e

        if event == self.key_ns + 'rendered_tracks_button':
            # mark tracks for use in render matrix
            line = ','.join(
                [track.GUID for track in rpr.Project().selected_tracks]
            )
            if not line:
                self.rendered_tracks_text.Update('master')
            else:
                self.rendered_tracks_text.Update(line)

        if event == self.key_ns + 'wildcards_spin':
            # add wildcard from Spin to Input
            self.region_mask.Update(
                value=values[self.key_ns + 'region_mask'] +  # type:ignore
                values[self.key_ns + 'wildcards_spin']  # type:ignore
            )

        if event == self.key_ns + 'arts_file':
            return self.load_arts(values)
        return None

    def load_arts(
        self, values: ValuesType
    ) -> ty.Tuple[LayoutType, ty.List[BaseArt]]:
        """Load python file with articulations.

        Parameters
        ----------
        values: ValuesType

        Returns
        -------
        Tuple[LayoutType, List[BaseArt]]
            Ready layout with articulations GUI and articulation instances
        """
        path = Path(
            ty.cast(str, values[self.key_ns + 'arts_file'])  # type:ignore
        )
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


class MainMenu:

    clear_settings = \
        'Clear settings from project (will remove unused names)'
    reset_settings = \
        'Reset settings to Defaults (sliders will be set to defaults)'

    def __init__(self) -> None:
        self.layout = [
            sg.MenuBar(
                [['Prefs', [self.clear_settings, self.reset_settings]]],
                background_color=sg.DEFAULT_BACKGROUND_COLOR,
                key='main_menu'
            )
        ]


def _load_values(window: sg.Window) -> None:
    """Get saved controls from project file.

    Parameters
    ----------
    window : sg.Window
    """
    values = rpr.Project().get_ext_state(GUI_SECTION, GUI_KEY, pickled=True)
    if values in (None, ''):
        return
    for key, val in values.items():  # type:ignore
        if key == 'main_menu':
            continue
        try:
            window[key].update(val)
        except AttributeError as e:
            warn(f'{type(e)}: Cannot set value for element: {e}')


def _make_window(
    loop_slicer: LoopSlicerGui, arts_handler: ArtsHandler, load_values: bool
) -> sg.Window:
    """Make sg.Window and initialize values if needed.

    Parameters
    ----------
    loop_slicer : LoopSlicerGui
    arts_handler : ArtsHandler
    load_values : bool
        If True — project will be checked for saved controls data.
    """
    layout = []
    menu = MainMenu()
    layout.append(menu.layout)
    for sub_lay in (loop_slicer.layout, arts_handler.layout):
        layout.extend(sub_lay)

    window = sg.Window('Sample Editor (by Levitanus)', layout)
    window.Finalize()
    if load_values:
        _load_values(window)
        arts_handler.load_btn.Update('Load arts')
    return window


def check_for_exception(result: ty.Optional[Exception]) -> None:
    if result is None:
        return
    sg.popup_error(str(result))


def ah_read(
    ah: ArtsHandler, event: str, values: ValuesType, serialized: ValuesType,
    ls: LoopSlicerGui, load_values: bool, window: sg.Window
) -> ty.Tuple[ArtsHandler, sg.Window]:
    ah_read_ret = ah.read(event, values)
    if isinstance(ah_read_ret, tuple) and isinstance(ah_read_ret[0], ty.List):
        ah = ArtsHandler(
            tabs_layout=ah_read_ret[0], arts_instances=ah_read_ret[1]
        )
        ls = LoopSlicerGui()
        if serialized is not None:
            rpr.Project().set_ext_state(
                GUI_SECTION, GUI_KEY, serialized, pickled=True
            )
        wind1 = _make_window(ls, ah, load_values)
        window.close()
        window = wind1
    else:
        check_for_exception(ah_read_ret)  # type:ignore
    return ah, window


def _serialize(serialized: ty.Dict[str, ty.Union[str, float, bool]]) -> None:
    rpr.Project().set_ext_state(GUI_SECTION, GUI_KEY, serialized, pickled=True)


def _un_serialize() -> None:
    rpr.Project().set_ext_state(GUI_SECTION, GUI_KEY, '', pickled=True)


def run(load_values: bool = True, theme: str = '') -> None:
    """Main GUI function, used to launch script.

    Parameters
    ----------
    load_values : bool, optional
        If loading of persistent values is needed.
    """
    if theme:
        sg.theme(theme)
    ls = LoopSlicerGui()
    ah = ArtsHandler()
    serialized: ValuesType
    if load_values:
        serialized = rpr.Project(  # type:ignore
        ).get_ext_state(GUI_SECTION, GUI_KEY, pickled=True)
        # print(serialized)
        if serialized and serialized[ah.key_ns + 'arts_file'] != '':
            tabs_layout, arts = ah.load_arts(serialized)
            ah = ArtsHandler(tabs_layout, arts)
    window = _make_window(ls, ah, load_values)

    serialized = None
    while True:
        event, values = ty.cast(ty.Tuple[str, ValuesType], window.read())
        if event == sg.WIN_CLOSED:
            # values = values
            break
        if event == MainMenu.clear_settings:
            if values is None:
                warn('Something strange happening: values are None')
                continue
            serialized = values
            _serialize(serialized)
        if event == MainMenu.reset_settings:
            print('resetting')
            window.close()
            run(theme=theme, load_values=False)
        serialized = values

        check_for_exception(ls.read(event, values))
        ah, window = ah_read(
            ah, event, values, serialized, ls, load_values, window
        )
    if serialized is not None:
        _serialize(serialized)
    window.close()
