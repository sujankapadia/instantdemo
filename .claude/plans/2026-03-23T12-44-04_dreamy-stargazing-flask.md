# Plan: Trim Loading Frames from Video Recording

## Context

`render.py` records one continuous video for the entire demo. Loading states (skeletons, spinners) from `goto` navigations appear in the final video because the video encoder captures every frame — `wait_for` blocks the Python script from advancing but doesn't prevent those frames from being recorded.

The fix: keep the single continuous recording, but track timestamps for when each action completes (page is ready), then use ffmpeg to trim out the loading frames in the merge phase.

## Approach

### Phase B: Track timestamps in `record_browser_video`

For each segment, record the time when the action finishes and the page is ready (after `wait_for` resolves). This is the start of the "clean" portion. The segment sleep then runs for `max(audio_duration, pause_after_ms)`, giving us the end of the clean portion.

Return the timestamps alongside the video path.

```python
def record_browser_video(...) -> tuple[Path, list[tuple[float, float]]]:
    recording_start = time.monotonic()
    timestamps = []

    for i, seg in enumerate(segments):
        _dispatch_action(page, seg)
        # Page is now ready — mark the clean start
        seg_start = time.monotonic() - recording_start
        time.sleep(wait_ms / 1000)
        seg_end = time.monotonic() - recording_start
        timestamps.append((seg_start, seg_end))

    return video_path, timestamps
```

### Phase C: Trim and stitch in `combine_audio_video`

1. For each segment, extract a trimmed clip from the continuous video:
   ```bash
   ffmpeg -ss {start} -t {duration} -i full_video.webm segment_i.webm
   ```
2. Concatenate the trimmed clips into one video (ffmpeg concat demuxer)
3. Mux the concatenated video with the combined audio (same as today)

### Main: Thread the new return value

`record_browser_video` now returns `(video_path, timestamps)` instead of just `video_path`. Pass both to `combine_audio_video`.

## File to modify

`/Users/skapadia/dev/personal/instantdemo/plugins/instantdemo/skills/generate-demo/scripts/render.py`

## Verification

1. Create a test script with a `goto` + `wait_for` that has a visible loading state
2. Render with current code — confirm loading frames appear
3. Render with new code — confirm loading frames are trimmed
4. Check that audio/video sync is preserved
