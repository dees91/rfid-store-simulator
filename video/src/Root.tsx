import { Composition } from 'remotion'
import { ScannerEmuOverview } from './ScannerEmuOverview'
import { SocialPreview } from './SocialPreview'
import { SOCIAL_PREVIEW, VIDEO } from './storyboard'

export function Root() {
  return (
    <>
      <Composition
        id="ScannerEmuOverview"
        component={ScannerEmuOverview}
        durationInFrames={VIDEO.durationInFrames}
        fps={VIDEO.fps}
        width={VIDEO.width}
        height={VIDEO.height}
      />
      <Composition id="ScannerEmuSocialPreview" component={SocialPreview} durationInFrames={1} fps={1} width={SOCIAL_PREVIEW.width} height={SOCIAL_PREVIEW.height} />
    </>
  )
}
