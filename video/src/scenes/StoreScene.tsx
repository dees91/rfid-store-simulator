import { interpolate, useCurrentFrame } from 'remotion'
import { AppViewport } from '../components/AppViewport'
import { SceneLayer } from '../components/SceneLayer'
import { Callout } from '../components/Typography'
import { copyString, getScene, sceneDuration } from '../storyboard'

const scene = getScene('store')

export function StoreScene() {
  const frame = useCurrentFrame()
  const swap = interpolate(frame, [70, 84], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
  return (
    <SceneLayer durationInFrames={sceneDuration(scene)}>
      <AppViewport asset={scene.assets?.[0] ?? ''} zoom={[1.0, 1.06]} panX={[0, -18]} panY={[0, 10]} opacity={1 - swap} />
      <AppViewport asset={scene.assets?.[1] ?? ''} zoom={[1.04, 1.08]} panX={[-18, -30]} panY={[10, 14]} opacity={swap} />
      <div style={{ position: 'absolute', left: 120, bottom: 64 }}>
        <Callout delay={16}>{copyString(scene, 'callout')}</Callout>
      </div>
    </SceneLayer>
  )
}
