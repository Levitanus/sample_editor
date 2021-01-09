import typing as ty
import pickle
import reapy as rpr
from reapy import reascript_api as RPR
import codecs

SECTION = 'levitanus_session_management'


def dumps(key: str, data: object, persist: bool = False) -> None:
    dump = pickle.dumps(data)
    state = codecs.encode(dump, 'base64').decode()
    rpr.set_ext_state(SECTION, key, state, persist=persist)


def loads(key: str) -> object:
    dump = rpr.get_ext_state(SECTION, key)
    if dump == '':
        return ''
    return pickle.loads(codecs.decode(dump.encode(), "base64"))


def proj_dumps(project: rpr.Project, key: str, data: object) -> int:
    dump = pickle.dumps(data)
    state = codecs.encode(dump, 'base64').decode()
    size: int = len(state)
    RPR.SetProjExtState(  # type:ignore
        project.id,  # noob formatting comment
        SECTION,
        key,
        state
    )
    size_str: str = str(str(size).encode().zfill(1000), 'utf-8')
    RPR.SetProjExtState(  # type:ignore
        project.id,  # noob formatting comment
        SECTION,
        key+'_size',
        size_str
    )
    return size


def proj_loads(project: rpr.Project, key: str) -> str:
    size_str: str
    (_, _, _, _, size_str, _) = RPR.GetProjExtState(  # type:ignore
        project.id, SECTION, key+'_size', 'valOutNeedBig', 1001
    )
    if not size_str:
        return ''
    size = int(size_str)
    (_, _, _, _, dump, _) = RPR.GetProjExtState(  # type:ignore
        project.id, SECTION, key, 'valOutNeedBig', size+1
    )
    # rpr.print('get_size_str: ', size_str)
    # rpr.print(size)
    if dump == '':
        return ''
    return pickle.loads(codecs.decode(dump.encode(), "base64"))
