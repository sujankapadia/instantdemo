import { forwardRef, useState } from 'react'
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

    if (errored) {
      return (
        <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border bg-muted/30 text-muted-foreground">
          <Film className="size-8 opacity-60" />
          <span className="text-sm">No video rendered yet</span>
          <span className="text-xs text-muted-foreground/80">
            Phase 5 produces <code className="font-mono">demo.mp4</code>
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
        className="aspect-video w-full rounded-md bg-black"
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
