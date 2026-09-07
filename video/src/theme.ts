import type { CSSProperties } from 'react'

// Mirrors the 3D UI's light HUD palette so the promo and the product read as
// one system: pale canvas, deep green accents, red/amber/green progress ramp.
export const colors = {
  canvas: '#F3F5F2',
  panel: '#FFFFFF',
  deep: '#0F1A16',
  ink: '#16211C',
  muted: '#5F6B66',
  border: '#D9DED9',
  green: '#12A75F',
  greenDeep: '#0E5A3C',
  amber: '#D89A28',
  red: '#D64C3F',
  terminal: '#0D0D0E',
  terminalText: '#F2F2F2',
  terminalMuted: '#A7A7AC',
  cyan: '#50B0E0',
} as const

export const fonts = {
  sans: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", system-ui, sans-serif',
  mono: 'ui-monospace, "SFMono-Regular", Menlo, Monaco, monospace',
} as const

export const fullFrame: CSSProperties = {
  position: 'absolute',
  inset: 0,
  width: '100%',
  height: '100%',
}
