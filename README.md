# MoH Arena Demo Reviewer

Local desktop demo review/player tool for MOHAA anti-cheat review. The app does
not parse or render MOHAA demos itself. It launches OpenMoHAA in windowed mode
and controls playback through OpenMoHAA's `com_pipefile` FIFO.

## What V1 Supports

- Launch OpenMoHAA with an isolated temporary `fs_homepath`.
- Copy the selected demo to `main/demos/review.dm_8`, including `.demo_aa`
  inputs.
- Play, pause, restart, approximate rewind/seek, and change speed from `0.1x`
  through `16x`.
- Toggle third person, show/hide scores, screenshot, and start/stop FFmpeg recording.
- Stop OpenMoHAA through the pipe `quit` command.
- Show an estimated demo timestamp in the Python UI.
- Optionally enable x-ray vision by copying `custom_pk3/zzz-Dark_Sniper_zztoggleskin_fix.pk3`
  into the temporary review `main/` directory for that launch only.
- Keep the temporary homepath after quit so screenshots remain available under
  the review `main/screenshots` folder.
- Save FFmpeg recordings to the inferred OpenMoHAA basepath under `main/videos`.

Real rewind and accurate seeking are not supported in v1. Q3/MOHAA demos are
stream based. The rewind buttons and **Approx Seek** control restart the demo,
fast-forward at `64x` until the requested estimated timestamp, then restore the
previous play/pause state and speed. They are useful for getting close to a
point in the demo, but they are not frame-accurate.

The timestamp in the Python UI is estimated from commands sent by the reviewer.
OpenMoHAA's pipe control path accepts commands but does not return an exact demo
server timestamp.

## Platform Notes

Pipe control is supported on macOS/Linux OpenMoHAA builds. The OpenMoHAA source
creates `com_pipefile` through `Sys_Mkfifo` on Unix-like systems, while the
Windows implementation returns `NULL`; Windows pipe control is therefore not
available in this v1 app.

The expected pipe path is:

```text
<fs_homepath>/main/moh_arena_pipe
```

## Beginner Setup

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

Install FFmpeg if you want recording:

```bash
brew install ffmpeg
```

If you do not have Homebrew yet, install it from <https://brew.sh/> first, then
run the `brew install ffmpeg` command above.

Run the app any time with:

```bash
source .venv/bin/activate
python -m moh_arena_demo_reviewer
```

## Linux Setup

From the workspace root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m moh_arena_demo_reviewer
```

Install FFmpeg with your distro package manager if you want recording, for
example:

```bash
sudo apt install ffmpeg
```

Linux recording uses FFmpeg `x11grab`, so it expects an X11 session with
`DISPLAY` set.

## Windows Status

Windows is not supported in v1 because OpenMoHAA does not implement
`com_pipefile` on Windows yet. Once OpenMoHAA grows a Windows pipe/control
mechanism, the Python app can be extended to use it.

In the GUI, choose:

- OpenMoHAA executable path, for example an `openmohaa` binary.
- Demo Reviewer infers `fs_basepath` from the executable's parent directory.
  For example, if the executable is
  `/Users/marcostreviso/Library/Application Support/openmohaa/openmohaa`, the
  inferred basepath is `/Users/marcostreviso/Library/Application Support/openmohaa`.
- Demo file path, for example `demos/mohdm6.dm_8`.
- Optional temp directory. Leave it blank to use the system temp directory.
- X-ray vision. When checked, the app copies `custom_pk3/zzz-Dark_Sniper_zztoggleskin_fix.pk3`
  into the temporary OpenMoHAA homepath. The copied pk3 is removed after the
  OpenMoHAA process closes.
- Resolution preset. Choose **Custom (-1)** for the width/height fields, or a
  built-in mode such as **640 x 480 (r_mode 4)**.

Click **Launch Demo**. The playback controls stay hidden until OpenMoHAA is
running and the FIFO appears. At that point the setup panel collapses, compact
playback controls appear, and the log panel remains hidden until toggled.

The rewind row provides quick jumps back by `5s`, `10s`, `30s`, `1m`, `5m`,
`10m`, and `30m`. The **Approx Seek** field accepts seconds, `mm:ss`, or
`hh:mm:ss`.

The **Start Rec** button uses FFmpeg to record the OpenMoHAA screen area to
`<inferred fs_basepath>/main/videos/<name>.mp4` and shows elapsed time plus
live file size.
Defaults are tuned for review-friendly file size: H.264/libx264, 30 fps,
`crf 28`, `veryfast`, `yuv420p`, and no audio. OBS can still be used manually
by selecting the OpenMoHAA window and recording outside this app.

If automatic OpenMoHAA window detection fails, click **Select Region** and drag
around the OpenMoHAA window. That manual region takes priority for subsequent
recordings during the current launch.

On macOS, exact window-only recording uses PyObjC/Quartz to find the OpenMoHAA
window rectangle. Detection checks the launched OpenMoHAA process, child
processes, and OpenMoHAA-like window owner names. If recording says it cannot
detect the bounds, open the log panel for the detailed reason. If Quartz is
unavailable, run `python -m pip install -r requirements.txt` in the active venv
and reopen the reviewer. FFmpeg may also ask for Screen Recording permission on
first use.

On macOS, the app retries for a few seconds to place OpenMoHAA top-center and
move the compact controller to bottom-center. This uses AppleScript through System
Events, so macOS may require Accessibility permission for the Python/terminal
process running the app. Playback still works if positioning is blocked.
The app remembers separate setup-window and playback-control-window geometry,
plus the last OpenMoHAA window bounds when macOS allows them to be inspected.

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
<inferred fs_basepath>/main/videos/<name>.mp4
```

The `.cfg` and `.urc` files provide fallback in-game binds/menu buttons through
`stuffcommand`, but the Python GUI's primary control path is the FIFO.

## Tests

```bash
python -m pytest
```

The tests do not require OpenMoHAA or MOHAA assets.
