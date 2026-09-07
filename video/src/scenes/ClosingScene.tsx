import { Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion'
import { SceneLayer } from '../components/SceneLayer'
import { colors } from '../theme'
import { copyString, getScene, sceneDuration } from '../storyboard'

const scene = getScene('closing')

export function ClosingScene() {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const image = spring({ frame: frame - 3, fps, config: { damping: 16, stiffness: 105, mass: 0.9 } })
  const copy = spring({ frame: frame - 10, fps, config: { damping: 18, stiffness: 95 } })
  const finalFade = interpolate(frame, [70, 88], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })

  return (
    <SceneLayer durationInFrames={sceneDuration(scene)} exitFrames={1} style={{ opacity: finalFade }}>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', gap: 70, padding: '0 120px' }}>
        <div
          style={{
            width: 720,
            height: 405,
            borderRadius: 24,
            overflow: 'hidden',
            border: `1px solid ${colors.border}`,
            boxShadow: '0 36px 100px #0F1A1633',
            opacity: image,
            scale: String(0.9 + image * 0.1),
            rotate: `${-2 * (1 - image)}deg`,
            flexShrink: 0,
          }}
        >
          <Img src={staticFile(scene.assets?.[0] ?? '')} style={{ width: 720, height: 405, objectFit: 'cover' }} />
        </div>
        <div style={{ opacity: copy, translate: `0px ${(1 - copy) * 28}px` }}>
          <div style={{ color: colors.greenDeep, fontSize: 28, fontWeight: 760, letterSpacing: 4 }}>{copyString(scene, 'product').toUpperCase()}</div>
          <div style={{ marginTop: 18, fontSize: 74, lineHeight: 1.06, fontWeight: 760, letterSpacing: -3.2, color: colors.ink }}>{copyString(scene, 'headline')}</div>
          <div style={{ marginTop: 30, color: colors.muted, fontSize: 30, fontWeight: 580 }}>{copyString(scene, 'footer')}</div>
        </div>
      </div>
    </SceneLayer>
  )
}
