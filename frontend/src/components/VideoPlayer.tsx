import { forwardRef, useEffect, useState } from 'react'
import { Film } from 'lucide-react'

interface VideoPlayerProps {
  src: string
  onTimeUpdate?: (currentTimeS: number) => void
}

/**
 * HTML5 video element with native controls. Forwards a ref so the
 * parent can call `.currentTime = N` to seek programmatically. Falls
 * back to a placeholder when the underlying URL 404s (no rendered
 * video yet).
 */
export const VideoPlayer = forwardRef<HTMLVideoElement, VideoPlayerProps>(
  function VideoPlayer({ src, onTimeUpdate }, ref) {
    const [errored, setErrored] = useState(false)

    // Reset the error state when `src` changes — otherwise once the
    // <video> hits onError, the placeholder is shown forever and a
    // new src (e.g. after Phase 5 finally renders) has nothing to
    // react to because the <video> element is unmounted.
    useEffect(() => {
      setErrored(false)
    }, [src])

    if (errored) {
      return (
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border bg-muted/30 text-muted-foreground">
          <Film className="size-8 opacity-60" />
          <span className="text-sm">No film yet</span>
          <span className="text-xs text-muted-foreground/80">
            Your demo appears here once it's recorded.
          </span>
        </div>
      )
    }

    return (
      <video
        ref={ref}
        src={src}
        controls
        preload="metadata"
        // h-full + object-contain lets the video fill the resizable
        // panel while preserving its aspect ratio. mx-auto centers
        // when the panel is wider than the video.
        className="h-full w-full object-contain mx-auto rounded-md bg-black"
        onError={() => setErrored(true)}
        onTimeUpdate={(event) => {
          if (onTimeUpdate) {
            onTimeUpdate(event.currentTarget.currentTime)
          }
        }}
      />
    )
  },
)
