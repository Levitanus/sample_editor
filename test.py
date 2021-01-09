import reapy as rpr
import librosa as lr
import soundfile as sf

from sample_editor import item_handler
from sample_editor import loop_finder
from sample_editor import loudness

from sample_editor.pitch_tracker import estimate_entire_root
from sample_editor import render_tools

from sample_editor import gui

# pr = rpr.Project()
# rendered_tracks = [
#     rpr.Track('S', project=pr),
#     rpr.Track('OH', project=pr),
#     rpr.Track('CL', project=pr)
# ]

# ih = item_handler.ItemsHandler()
# lf = loop_finder.LoopFinder(ih)
# st_ofst, end_ofst = lf.get_loop(
#     corr_wind_sec=0.11, slide_wind_sec=0.4, corr_min_treshold=0.3
# )
# print(st_ofst, end_ofst)
# ls = loop_finder.LoopSlicer(ih, lf)
# ls.cut_and_fade(st_ofst, end_ofst, crs_length=.2, crs_shape=1)

# rms = loudness.get_rms(ih)
# median = loudness.get_rms(ih, median=True)
# first_val_time = loudness.get_first_rms_value_ms(ih, median, want_marker='#')
# print(
#     # f'rms: {amplitude_to_db(rms)}',
#     f'median: {amplitude_to_db(median)}',
#     f'first_val_time: {first_val_time}',
#     sep='\n'
# )
# sr = 22050 // 2
# audio = item_handler.ItemHandler(sr=sr).load_audio()
# root = estimate_entire_root(audio, sr)
# render_tools.make_region_from_selected_items_or_ts(
#     f'test {root}', rendered_tracks
# )

gui.run(False)