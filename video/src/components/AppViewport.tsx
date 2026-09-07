import type { ReactNode } from 'react'
import { Img, interpolate, staticFile, useCurrentFrame } from 'remotion'
import { colors } from '../theme'

type FrameProps = {
  children: ReactNode
  opacity?: number
  left?: number
  top?: number
  width?: number
  height?: number
}

// A browser-window frame the way the 3D UI is actually used: a local tab.
export function BrowserFrame({ children, opacity = 1, left = 160, top = 70, width = 1600, height = 940 }: FrameProps) {
  return (
    <div
      style={{
        position: 'absolute',
        left,
        top,
        width,
        height,
        overflow: 'hidden',
        borderRadius: 22,
        border: `1px solid ${colors.border}`,
        background: colors.panel,
        boxShadow: '0 40px 120px #0F1A1633, 0 0 0 1px #FFFFFF70 inset',
        opacity,
      }}
    >
      <div style={{ height: 46, display: 'flex', alignItems: 'center', gap: 10, padding: '0 18px', background: '#EEF1EE', borderBottom: `1px solid ${colors.border}` }}>
        {['#E06C75', '#E5C07B', '#67C587'].map((color) => (
          <span key={color} style={{ width: 12, height: 12, borderRadius: '50%', background: color }} />
        ))}
        <span style={{ marginLeft: 14, padding: '4px 14px', borderRadius: 8, background: colors.panel, border: `1px solid ${colors.border}`, color: colors.muted, fontSize: 17 }}>
          127.0.0.1:8000
        </span>
      </div>
      <div style={{ position: 'absolute', left: 0, top: 46, right: 0, bottom: 0, overflow: 'hidden' }}>{children}</div>
    </div>
  )
}

type ViewportProps = {
  asset: string
  zoom?: readonly [number, number]
  panX?: readonly [number, number]
  panY?: readonly [number, number]
  opacity?: number
}

export function AppViewport({ asset, zoom = [1, 1.035], panX = [0, 0], panY = [0, 0], opacity = 1 }: ViewportProps) {
  const frame = useCurrentFrame()
  return (
    <BrowserFrame opacity={opacity}>
      <Img
        src={staticFile(asset)}
        style={{
          width: 1600,
          height: 900,
          objectFit: 'cover',
          objectPosition: 'center center',
          translate: `${interpolate(frame, [0, 120], [...panX], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })}px ${interpolate(frame, [0, 120], [...panY], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })}px`,
          scale: String(interpolate(frame, [0, 120], [...zoom], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })),
          transformOrigin: 'center 45%',
        }}
      />
    </BrowserFrame>
  )
}
