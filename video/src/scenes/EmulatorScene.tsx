import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion'
import { SceneLayer } from '../components/SceneLayer'
import { Eyebrow, Headline } from '../components/Typography'
import { colors, fonts } from '../theme'
import { copyString, getScene, sceneDuration } from '../storyboard'

const scene = getScene('emulator')

function Node({ label, sub, delay, accent, x, width = 360 }: { label: string; sub?: string; delay: number; accent: string; x: number; width?: number }) {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const progress = spring({ frame: frame - delay, fps, config: { damping: 16, stiffness: 120 } })
  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: 0,
        width,
        padding: '30px 34px',
        borderRadius: 24,
        background: colors.panel,
        border: `1px solid ${colors.border}`,
        boxShadow: '0 24px 70px #0F1A1622',
        opacity: progress,
        translate: `0px ${(1 - progress) * 24}px`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <span style={{ width: 14, height: 14, borderRadius: '50%', background: accent, boxShadow: `0 0 20px ${accent}` }} />
        <div style={{ fontSize: 36, fontWeight: 740, color: colors.ink }}>{label}</div>
      </div>
      {sub ? <div style={{ marginTop: 10, fontSize: 24, color: colors.muted, fontWeight: 560 }}>{sub}</div> : null}
    </div>
  )
}

export function EmulatorScene() {
  const frame = useCurrentFrame()
  const dash = interpolate(frame, [30, 90], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
  const pulse = (frame % 40) / 40

  return (
    <SceneLayer durationInFrames={sceneDuration(scene)}>
      <div style={{ position: 'absolute', left: 120, top: 150, display: 'flex', flexDirection: 'column', gap: 26 }}>
        <Eyebrow delay={4}>{copyString(scene, 'eyebrow')}</Eyebrow>
        <Headline width={1500} delay={8}>
          {copyString(scene, 'headline')}
        </Headline>
      </div>

      <div style={{ position: 'absolute', left: 120, top: 560, width: 1680, height: 200 }}>
        <Node label={copyString(scene, 'app')} sub="any BLE host" delay={22} accent={colors.red} x={0} />
        <Node label={copyString(scene, 'host')} sub={copyString(scene, 'radio')} delay={34} accent={colors.green} x={1120} width={560} />

        <svg width={760} height={120} style={{ position: 'absolute', left: 360, top: 20 }} aria-hidden="true">
          <line x1={0} y1={60} x2={760 * dash} y2={60} stroke={colors.greenDeep} strokeWidth={5} strokeDasharray="18 14" strokeLinecap="round" />
          <circle cx={760 * Math.min(dash, pulse)} cy={60} r={10} fill={colors.amber} opacity={dash >= 1 ? 1 : 0} />
        </svg>
        <div
          style={{
            position: 'absolute',
            left: 420,
            top: 90,
            width: 640,
            textAlign: 'center',
            fontFamily: fonts.mono,
            fontSize: 26,
            fontWeight: 700,
            color: colors.greenDeep,
            opacity: dash,
          }}
        >
          {copyString(scene, 'link')}
        </div>
      </div>
    </SceneLayer>
  )
}
