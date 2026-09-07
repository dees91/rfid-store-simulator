import { interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion'
import { SceneLayer } from '../components/SceneLayer'
import { Eyebrow, Headline } from '../components/Typography'
import { colors, fonts } from '../theme'
import { copyLines, copyString, getScene, sceneDuration } from '../storyboard'

const scene = getScene('cli')

export function CliScene() {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  const panel = spring({ frame: frame - 3, fps, config: { damping: 18, stiffness: 100 } })
  const command = copyString(scene, 'command')
  const typed = Math.floor(interpolate(frame, [10, 40], [0, command.length], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }))
  const output = copyLines(scene, 'output')

  return (
    <SceneLayer durationInFrames={sceneDuration(scene)}>
      <div style={{ position: 'absolute', left: 120, top: 250, display: 'flex', flexDirection: 'column', gap: 24 }}>
        <Eyebrow delay={4}>{copyString(scene, 'eyebrow')}</Eyebrow>
        <Headline width={640} delay={8}>
          {copyString(scene, 'headline')}
        </Headline>
      </div>

      <div
        style={{
          position: 'absolute',
          left: 860,
          top: 190,
          width: 940,
          height: 640,
          borderRadius: 24,
          overflow: 'hidden',
          border: `1px solid #2A2A2E`,
          background: colors.terminal,
          boxShadow: '0 40px 120px #0F1A1640',
          opacity: panel,
          translate: `${(1 - panel) * 80}px 0px`,
        }}
      >
        <div style={{ height: 58, display: 'flex', alignItems: 'center', gap: 12, padding: '0 22px', background: '#212123', borderBottom: '1px solid #38383B' }}>
          {['#E06C75', '#E5C07B', '#67C587'].map((color) => (
            <span key={color} style={{ width: 14, height: 14, borderRadius: '50%', background: color }} />
          ))}
          <span style={{ marginLeft: 14, color: colors.terminalMuted, fontSize: 18 }}>scanner-emu</span>
        </div>
        <div style={{ padding: '44px 46px', fontFamily: fonts.mono, fontSize: 27, lineHeight: 1.8, color: colors.terminalText }}>
          <div style={{ minHeight: 50 }}>
            {command.slice(0, typed)}
            <span style={{ color: colors.amber, opacity: frame % 14 < 9 ? 1 : 0 }}>▋</span>
          </div>
          <div style={{ marginTop: 18, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {output.map((line, index) => {
              const visible = interpolate(frame, [44 + index * 8, 50 + index * 8], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
              const isPrompt = line.startsWith('scanner-emu>')
              return (
                <div key={line} style={{ color: index === 0 ? '#67C587' : isPrompt ? colors.terminalText : colors.terminalMuted, opacity: visible, translate: `0px ${(1 - visible) * 10}px` }}>
                  {isPrompt ? (
                    <>
                      <span style={{ color: colors.cyan }}>scanner-emu&gt;</span>
                      {line.slice('scanner-emu>'.length)}
                    </>
                  ) : (
                    line
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </SceneLayer>
  )
}
