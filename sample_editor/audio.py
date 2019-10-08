import reapy as rpr
import reapy.reascript_api as RPR
import typing as ty

sectionOut, startOut, lengthOut, fadeOut, reverseOut = 0, 0, 0, 0, 0

project = rpr.Project()
print(project.n_selected_items)
item = project.get_selected_item(0)
take = item.active_take
# tp = rpr.Take()
# tp.source()
source = take.source
print(take.source)
src_f = source.filename
print(source.length)


def get_source_bounds(take: rpr.Take) -> ty.Tuple[float, float, float]:
    """Return start, end and length in seconds of the source of given item."""
    _, _, _, start, length, _, _ = RPR.BR_GetMediaSourceProperties(
        take.id, 1, 1, 1, 1, 1)
    return start, start + length, length


# props = RPR.BR_GetMediaSourceProperties(take.id, sectionOut, startOut,
#                                         lengthOut, fadeOut, reverseOut)
start, end, length = get_source_bounds(take)
a_a = take.add_audio_accessor()
print(a_a.start_time, a_a.end_time)
print(start, end, length)
