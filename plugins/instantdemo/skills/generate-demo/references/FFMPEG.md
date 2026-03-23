# How ffmpeg Is Used in the Rendering Pipeline

Technical reference for how `render.py` uses ffmpeg and ffprobe for audio processing, video trimming, and final output assembly.

## Overview

The rendering pipeline calls ffmpeg/ffprobe in several places:

1. **Audio duration measurement** — ffprobe measures each TTS clip's duration to calculate Playwright timing
2. **Audio format normalization** — converts non-WAV clips (e.g., MP3 from ElevenLabs) to WAV
3. **Silence generation** — creates silent WAV clips for gaps between segments
4. **Audio concatenation** — stitches audio clips + silence gaps into one continuous track
5. **Video trimming + concatenation + mux** — trims loading frames from the video, concatenates clean segments, and merges with audio into the final MP4

## Audio Pipeline

### Duration measurement (ffprobe)

```bash
ffprobe -v quiet -show_entries format=duration -of csv=p=0 segment_0.wav
```

Returns the duration in seconds (e.g., `3.456`). Used to calculate how long Playwright should sleep on each segment: `max(audio_duration, pause_after_ms)`.

### Format normalization

ElevenLabs returns MP3; Piper and Google return WAV. The concat demuxer requires uniform formats, so non-WAV clips are converted:

```bash
ffmpeg -y -i segment_0.mp3 segment_0.wav
```

### Silence generation

When `pause_after_ms` exceeds the audio duration, a silence clip fills the gap:

```bash
ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=stereo -t 0.5 silence_0.wav
```

- `anullsrc` — generates silence (null audio source)
- `r=44100:cl=stereo` — 44.1kHz stereo to match TTS output
- `-t 0.5` — duration in seconds

### Audio concatenation

All audio clips and silence gaps are listed in a concat file:

```
file '/tmp/instantdemo-xxx/segment_0.wav'
file '/tmp/instantdemo-xxx/silence_0.wav'
file '/tmp/instantdemo-xxx/segment_1.wav'
```

Then concatenated with stream copy (lossless, since all clips are WAV):

```bash
ffmpeg -y -f concat -safe 0 -i audio_concat.txt -c copy combined_audio.wav
```

## Video Pipeline

### The trimming problem

Playwright records one continuous video for the entire demo. Loading states (skeletons, spinners) from page navigations appear in the recording because the video encoder captures every frame — there's no way to pause recording mid-session.

The solution: track timestamps for when each action completes (page is ready), then use ffmpeg to extract only the "clean" portions of the video.

### Why stream copy doesn't work for trimming

Video compression uses two types of frames:

- **Keyframes (I-frames)** — complete images stored in full, like a JPEG
- **Delta frames (P/B-frames)** — only store what changed since the last keyframe, much smaller

A typical WebM video has keyframes every 2-5 seconds with delta frames in between. When using `-c copy` (stream copy), ffmpeg doesn't decode the video — it copies compressed data. But it can only start copying from a keyframe, because delta frames are meaningless without their preceding keyframe.

If you ask to cut at 5.3s but the nearest keyframe is at 4.0s, ffmpeg snaps back to 4.0s — giving you 1.3s of unwanted footage (loading frames from the previous segment). This causes:

- Clips starting from a previous segment's content
- Duplicate page views
- Audio/video desync that accumulates over segments

### The filter_complex approach

Instead of extracting clips to intermediate files and re-encoding multiple times, we use a single ffmpeg command with `filter_complex` to trim, concatenate, and encode in one pass.

For a 3-segment video with timestamps:
```
Segment 0: action done at 2.5s, sleep ends at 7.0s
Segment 1: action done at 9.0s, sleep ends at 14.0s
Segment 2: action done at 16.5s, sleep ends at 21.0s
```

The filter_complex is:

```
[0:v]trim=start=2.500:duration=4.500,setpts=PTS-STARTPTS[v0];
[0:v]trim=start=9.000:duration=5.000,setpts=PTS-STARTPTS[v1];
[0:v]trim=start=16.500:duration=4.500,setpts=PTS-STARTPTS[v2];
[v0][v1][v2]concat=n=3:v=1:a=0[outv]
```

Breaking it down:

- **`[0:v]`** — the video stream from input 0 (the Playwright WebM)
- **`trim=start=2.500:duration=4.500`** — extracts frames from 2.5s to 7.0s. The `trim` filter operates on decoded frames, so it's frame-accurate — no keyframe dependency.
- **`setpts=PTS-STARTPTS`** — resets presentation timestamps to start from 0. Without this, segment 0's frames would retain timestamps starting at 2.5s, and ffmpeg would insert 2.5s of blank space at the beginning. Each trimmed segment needs its own timeline starting at zero.
- **`[v0]`** — labels this processed stream for later reference
- **`[v0][v1][v2]concat=n=3:v=1:a=0[outv]`** — concatenates the three streams sequentially. `n=3` = three inputs, `v=1` = one video stream output, `a=0` = no audio (handled separately). Output labeled `[outv]`.

The full ffmpeg command:

```bash
ffmpeg -y \
  -i video.webm \
  -i combined_audio.wav \
  -filter_complex "[0:v]trim=start=2.500:duration=4.500,setpts=PTS-STARTPTS[v0];[0:v]trim=start=9.000:duration=5.000,setpts=PTS-STARTPTS[v1];[0:v]trim=start=16.500:duration=4.500,setpts=PTS-STARTPTS[v2];[v0][v1][v2]concat=n=3:v=1:a=0[outv]" \
  -map "[outv]" \
  -map 1:a \
  -c:v libx264 -crf 18 -preset slow \
  -c:a aac -b:a 192k \
  -shortest \
  output.mp4
```

- **`-map [outv]`** — use the trimmed/concatenated video
- **`-map 1:a`** — use the audio from input 1 (combined_audio.wav)
- **`-c:v libx264 -crf 18 -preset slow`** — encode to H.264 once, CRF 18 for high quality
- **`-c:a aac -b:a 192k`** — encode audio to AAC at 192kbps
- **`-shortest`** — truncate to the shorter of video or audio

### Evolution of the trimming approach

1. **First attempt**: `-ss -t -c copy` — stream copy, fast but cuts only on keyframes. Caused desync and duplicate frames.
2. **Second attempt**: `-ss -t -c:v libvpx -crf 10` — re-encode each clip for frame-accurate cuts, then re-encode again to concat, then again to H.264. Three encoding passes, slow, quality loss.
3. **Current approach**: `filter_complex` with `trim` + `setpts` + `concat` — single decode/encode pass. Frame-accurate, fast, best quality.
