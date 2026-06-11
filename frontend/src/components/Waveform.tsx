import { useEffect, useRef } from 'react'

// Show the medium (DESIGN.md principle 16): while a voice preview
// plays, draw its real waveform — the interface visibly contains
// audio. One shared AudioContext; each Audio element gets its
// analyser attached exactly once (createMediaElementSource is
// once-per-element).

let sharedCtx: AudioContext | null = null
const attached = new WeakMap<HTMLAudioElement, AnalyserNode>()

function analyserFor(audio: HTMLAudioElement): AnalyserNode | null {
  try {
    sharedCtx ??= new AudioContext()
    if (sharedCtx.state === 'suspended') void sharedCtx.resume()
    let analyser = attached.get(audio)
    if (!analyser) {
      const source = sharedCtx.createMediaElementSource(audio)
      analyser = sharedCtx.createAnalyser()
      analyser.fftSize = 64
      source.connect(analyser)
      analyser.connect(sharedCtx.destination)
      attached.set(audio, analyser)
    }
    return analyser
  } catch {
    return null
  }
}

const BARS = 12

export function WaveformBars({ audio }: { audio: HTMLAudioElement }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const analyser = analyserFor(audio)
    if (!canvas || !analyser) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const data = new Uint8Array(analyser.frequencyBinCount)
    const accent = getComputedStyle(document.documentElement)
      .getPropertyValue('--primary')
      .trim()
    let raf = 0

    const draw = () => {
      analyser.getByteFrequencyData(data)
      const { width, height } = canvas
      ctx.clearRect(0, 0, width, height)
      ctx.fillStyle = accent || '#e0a458'
      const step = Math.floor(data.length / BARS)
      const barWidth = width / BARS - 2
      for (let i = 0; i < BARS; i++) {
        const value = data[i * step]! / 255
        const barHeight = Math.max(2, value * height)
        ctx.fillRect(
          i * (barWidth + 2),
          height - barHeight,
          barWidth,
          barHeight,
        )
      }
      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [audio])

  return (
    <canvas
      ref={canvasRef}
      width={64}
      height={16}
      className="h-4 w-16"
      aria-hidden="true"
    />
  )
}
