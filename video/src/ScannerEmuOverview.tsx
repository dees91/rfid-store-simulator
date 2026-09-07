import { AbsoluteFill, Sequence } from 'remotion'
import { colors } from './theme'
import { STORYBOARD, sceneDuration } from './storyboard'
import { ProblemScene } from './scenes/ProblemScene'
import { EmulatorScene } from './scenes/EmulatorScene'
import { StoreScene } from './scenes/StoreScene'
import { ScanScene } from './scenes/ScanScene'
import { CliScene } from './scenes/CliScene'
import { ClosingScene } from './scenes/ClosingScene'

const components = {
  problem: ProblemScene,
  emulator: EmulatorScene,
  store: StoreScene,
  scan: ScanScene,
  cli: CliScene,
  closing: ClosingScene,
} as const

export function ScannerEmuOverview() {
  return (
    <AbsoluteFill style={{ backgroundColor: colors.canvas }}>
      {STORYBOARD.map((scene) => {
        const Component = components[scene.id]
        return (
          <Sequence key={scene.id} name={scene.id} from={scene.start} durationInFrames={sceneDuration(scene)}>
            <Component />
          </Sequence>
        )
      })}
    </AbsoluteFill>
  )
}
