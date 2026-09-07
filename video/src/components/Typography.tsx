import type { ReactNode } from 'react'
import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion'
import { colors } from '../theme'

export function Eyebrow({ children, delay = 0 }: { children: ReactNode; delay?: number }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const progress = spring({ frame: frame - delay, fps, config: { damping: 18, stiffness: 130 } })
  return (
    <div style={{ color: colors.greenDeep, fontSize: 24, fontWeight: 750, letterSpacing: 4.5, opacity: progress, translate: `0px ${(1 - progress) * 16}px` }}>
      {children}
    </div>
  )
}

export function Headline({ children, delay = 4, width = 1120, size = 84 }: { children: ReactNode; delay?: number; width?: number; size?: number }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const progress = spring({ frame: frame - delay, fps, config: { damping: 17, stiffness: 105, mass: 0.9 } })
  return (
    <div style={{ width, fontSize: size, lineHeight: 1.05, fontWeight: 760, letterSpacing: -3.6, color: colors.ink, opacity: progress, translate: `0px ${(1 - progress) * 30}px` }}>
      {children}
    </div>
  )
}

export function Callout({ children, delay = 0, accent = colors.green }: { children: ReactNode; delay?: number; accent?: string }) {
  const frame = useCurrentFrame()
  const opacity = interpolate(frame, [delay, delay + 8], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
  const scale = interpolate(frame, [delay, delay + 10], [0.94, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 14,
        padding: '18px 26px',
        border: `1px solid ${accent}80`,
        borderRadius: 999,
        background: '#FFFFFFF0',
        boxShadow: '0 18px 60px #0F1A1622',
        fontSize: 34,
        fontWeight: 700,
        color: colors.ink,
        opacity,
        scale: String(scale),
      }}
    >
      <span style={{ width: 12, height: 12, borderRadius: '50%', background: accent, boxShadow: `0 0 22px ${accent}` }} />
      {children}
    </div>
  )
}

export function Chip({ children, delay = 0, accent = colors.green }: { children: ReactNode; delay?: number; accent?: string }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const progress = spring({ frame: frame - delay, fps, config: { damping: 16, stiffness: 140 } })
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 12,
        padding: '14px 24px',
        borderRadius: 999,
        border: `1px solid ${colors.border}`,
        background: colors.panel,
        fontSize: 28,
        fontWeight: 650,
        color: colors.ink,
        opacity: progress,
        translate: `0px ${(1 - progress) * 18}px`,
      }}
    >
      <span style={{ width: 10, height: 10, borderRadius: '50%', background: accent }} />
      {children}
    </div>
  )
}
