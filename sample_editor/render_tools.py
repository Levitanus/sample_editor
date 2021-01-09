import typing as ty
import reapy as rpr

from .loudness import get_rms, get_first_rms_value_ms
from .item_handler import ItemsHandler


def make_region_from_selected_items_or_ts(
    name: str,
    tracks_in_matrix: ty.Optional[ty.List[rpr.Track]] = None
) -> rpr.Region:
    with rpr.inside_reaper():
        pr = rpr.Project()
        ts = pr.time_selection
        # if no time selection
        start, end = (ts.start, ts.end)
        if (start, end) == (0, 0):
            start, end = ItemsHandler().get_bounds(check_for_indentity=False)
        region = pr.add_region(start, end, name=name)
        if tracks_in_matrix:
            region.add_rendered_tracks(tracks_in_matrix)
    return region
