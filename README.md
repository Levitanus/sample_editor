# sample_editor
reaper python plugin for cutting samples and get metadata


Docs are coming with the first minor release.

## example of work:

[![Youtube exmple of work](http://img.youtube.com/vi/b96FaK4dTUc/0.jpg)](http://www.youtube.com/watch?v=b96FaK4dTUc "Video Title")

## Installation Guide

Sample editor is Reaper Python extension, so You're first need [Reaper](reaper.fm/) and [Python](python.org). Make sure the both have the same architacture: if Reaper is x64 — you need Python x64.

When both programms are installed, run Reaper and open command line (or terminal).

```
pip install psutil 
pip install git+https://github.com/Levitanus/sample_editor
python -c "import reapy; reapy.configure_reaper()"
```

then restart Reaper

Then run `sample_editor` from cmd or terminal and you're there.

## Usage

Since the work in progress, and API is unstable, everythin can cgange. Hovewer, the **sample editor** is designed as module system, that brings useful functions that can be organized in «articulations» — GUI frames corresponds to making particular sample grous (like legato\staccato\attack\release etc). There is «gentlemen toolkit» in the file test_arts.py which can be used in production and as inspiration.

After GUI is loaded — articulation handlers can be loaded via `load arts` button.
