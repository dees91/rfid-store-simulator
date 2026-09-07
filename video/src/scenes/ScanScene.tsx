import { Video } from '@remotion/media'
import { interpolate, staticFile, useCurrentFrame } from 'remotion'
import { BrowserFrame } from '../components/AppViewport'
import { SceneLayer } from '../components/SceneLayer'
import { Callout } from '../components/Typography'
import { colors } from '../theme'
import { copyString, getScene, sceneDuration } from '../storyboard'

const scene = getScene('scan')

export function ScanScene() {
  const frame = useCurrentFrame()
  const duration = sceneDuration(scene)
  const first = interpolate(frame, [10, 18, 84, 92], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
  const second = interpolate(frame, [96, 104, duration - 14, duration - 8], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
  return (
    <SceneLayer durationInFrames={duration}>
      <BrowserFrame>
        <Video
          src={staticFile(scene.assets?.[0] ?? '')}
          trimBefore={0}
          style={{ width: 1600, height: 900, objectFit: 'cover' }}
          muted
        />
      </BrowserFrame>
      <div style={{ position: 'absolute', left: 120, bottom: 64, opacity: first }}>
        <Callout accent={colors.amber}>{copyString(scene, 'calloutScan')}</Callout>
      </div>
      <div style={{ position: 'absolute', left: 120, bottom: 64, opacity: second }}>
        <Callout accent={colors.green}>{copyString(scene, 'calloutProgress')}</Callout>
      </div>
    </SceneLayer>
  )
}
