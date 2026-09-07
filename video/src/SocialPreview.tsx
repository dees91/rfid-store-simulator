import { AbsoluteFill, Img, staticFile } from 'remotion'
import { SOCIAL_PREVIEW } from './storyboard'
import { colors, fonts } from './theme'

export function SocialPreview() {
  return (
    <AbsoluteFill style={{ backgroundColor: colors.canvas, color: colors.ink, fontFamily: fonts.sans, overflow: 'hidden' }}>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: `radial-gradient(circle at 80% 20%, ${colors.green}22, transparent 38%), radial-gradient(circle at 10% 90%, ${colors.amber}18, transparent 34%)`,
        }}
      />
      <div style={{ position: 'absolute', top: 0, left: 0, width: 14, height: 640, backgroundColor: colors.green }} />

      <div style={{ position: 'absolute', left: 72, top: 78, width: 620 }}>
        <div style={{ color: colors.greenDeep, fontSize: 22, fontWeight: 760, letterSpacing: 4 }}>{SOCIAL_PREVIEW.copy.product.toUpperCase()}</div>
        <div style={{ marginTop: 22, fontSize: 60, lineHeight: 1.05, fontWeight: 760, letterSpacing: -2.4 }}>{SOCIAL_PREVIEW.copy.headline}</div>
        <div style={{ marginTop: 26, fontSize: 24, fontWeight: 620, color: colors.muted }}>{SOCIAL_PREVIEW.copy.supporting}</div>
        <div style={{ marginTop: 12, fontSize: 22, fontWeight: 560, color: colors.muted }}>{SOCIAL_PREVIEW.copy.surfaces}</div>
      </div>

      <div
        style={{
          position: 'absolute',
          left: 736,
          top: 92,
          width: 800,
          height: 450,
          borderRadius: 22,
          overflow: 'hidden',
          border: `1px solid ${colors.border}`,
          boxShadow: '0 30px 80px #0F1A1633',
          rotate: '-3deg',
        }}
      >
        <Img src={staticFile(SOCIAL_PREVIEW.asset)} style={{ width: 800, height: 450, objectFit: 'cover' }} />
      </div>
    </AbsoluteFill>
  )
}
