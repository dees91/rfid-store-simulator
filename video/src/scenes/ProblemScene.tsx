import { SceneLayer } from '../components/SceneLayer'
import { Chip, Eyebrow, Headline } from '../components/Typography'
import { colors } from '../theme'
import { copyLines, copyString, getScene, sceneDuration } from '../storyboard'

const scene = getScene('problem')
const accents = [colors.green, colors.amber, colors.red, colors.greenDeep]

export function ProblemScene() {
  return (
    <SceneLayer durationInFrames={sceneDuration(scene)}>
      <div style={{ position: 'absolute', left: 120, top: 250, display: 'flex', flexDirection: 'column', gap: 30 }}>
        <Eyebrow delay={4}>{copyString(scene, 'eyebrow')}</Eyebrow>
        <Headline width={1400} delay={8} size={96}>
          {copyString(scene, 'headline')}
        </Headline>
        <div style={{ display: 'flex', gap: 18, marginTop: 26 }}>
          {copyLines(scene, 'chips').map((chip, index) => (
            <Chip key={chip} delay={26 + index * 5} accent={accents[index % accents.length]}>
              {chip}
            </Chip>
          ))}
        </div>
      </div>
    </SceneLayer>
  )
}
