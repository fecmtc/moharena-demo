# MoH Arena Demo Reviewer

Local desktop demo review/player tool for MOHAA anti-cheat review. The app does
not parse or render MOHAA demos itself. It launches OpenMoHAA in windowed mode
and controls playback through OpenMoHAA's `com_pipefile` FIFO.

Therefore, this tool works only on **macOS** and **Linux** for now.

The OpenMoHAA source creates `com_pipefile` through `Sys_Mkfifo` on Unix-like systems, while the
Windows implementation returns `NULL`; Windows pipe control is therefore not available in this v1 app.

## Screenshots

| Launch setup | Playback controls and log | OpenMoHAA with compact controller |
| --- | --- | --- |
| ![Launch setup screen](figs/screenshot1.jpeg) | ![Playback controls and log panel](figs/screenshot2.jpeg) | ![OpenMoHAA playback with compact controller](figs/screenshot3.jpeg) |

## Setup

You need four things:

1. Python 3.10 or newer.
2. OpenMoHAA installed locally.
3. MOHAA game assets in the same folder as the OpenMoHAA executable.
4. FFmpeg if you want video recording.

The app does not include MOHAA game assets. In the GUI you only select the
OpenMoHAA executable; the app infers the MOHAA basepath from that executable's
folder.

## macOS Setup

From the workspace root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m moh_arena_demo_reviewer
```

You can also install directly from `pyproject.toml`:

```bash
python -m pip install -e .
```

For running tests, install the dev extra:

```bash
python -m pip install -e ".[dev]"
```

On macOS, these installs include `pyobjc-framework-Quartz` so the app can find
the exact OpenMoHAA window rectangle for FFmpeg recording.

## Install FFmpeg if you want recording:

On MacOS:
```bash
brew install ffmpeg
```

On Linux:
```bash
sudo apt install ffmpeg
```

Linux recording uses FFmpeg `x11grab`, so it expects an X11 session with
`DISPLAY` set.



## Launch Shape

The app launches OpenMoHAA with arguments equivalent to:

```bash
openmohaa \
  +set fs_basepath "/path/to/MOHAA" \
  +set fs_homepath "/tmp/moh-arena-review-xxxx" \
  +set r_fullscreen 0 \
  +set r_mode -1 \
  +set r_customwidth 1280 \
  +set r_customheight 720 \
  +set r_noborder 0 \
  +set in_nograb 1 \
  +set com_pipefile moh_arena_pipe \
  +set cheats 1 \
  +set sv_cheats 1 \
  +set timedemo 0 \
  +set timescale 1 \
  +set cl_freezeDemo 0 \
  +exec moh_arena_demo_review.cfg \
  +demo review
```

## Generated Files

For each launch, the app creates:

```text
<homepath>/main/demos/review.dm_8
<homepath>/main/moh_arena_demo_review.cfg
<homepath>/main/autoexec.cfg
<homepath>/main/ui/moh_arena_demo_review.urc
<homepath>/main/screenshots/
```

FFmpeg recordings are saved outside that temporary homepath:

```text
<homepath>/main/videos/<name>.mp4
```


## Tests

```bash
python -m pytest
```

The tests do not require OpenMoHAA or MOHAA assets.
