import { useState } from 'react'
import { cn } from '@/lib/utils'

/**
 * Blur-up image (DESIGN.md principle 17): a muted placeholder holds
 * the layout, the image fades in on load. Errors keep the frame.
 */
export function FadeImg({
  className,
  ...props
}: React.ImgHTMLAttributes<HTMLImageElement>) {
  const [loaded, setLoaded] = useState(false)
  return (
    <img
      {...props}
      onLoad={(e) => {
        setLoaded(true)
        props.onLoad?.(e)
      }}
      className={cn(
        'bg-muted transition-opacity duration-300',
        loaded ? 'opacity-100' : 'opacity-0',
        className,
      )}
    />
  )
}
