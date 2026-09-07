export const VIDEO = {
  revision: 3,
  fps: 30,
  width: 1920,
  height: 1080,
  durationInFrames: 660,
} as const

export const SOCIAL_PREVIEW = {
  width: 1280,
  height: 640,
  copy: {
    product: 'RFID Store Simulator',
    headline: 'The RFID scanner, without the scanner.',
    supporting: 'Nordic ID EXA51 / EXA81 · BLE · NUR · Python',
    surfaces: '3D store · CLI REPL · USB dongle or Android emulator',
  },
  asset: 'ui/3d-store-final.png',
} as const

export type SceneID = 'problem' | 'emulator' | 'store' | 'scan' | 'cli' | 'closing'

export type StoryScene = {
  id: SceneID
  start: number
  end: number
  copy: Readonly<Record<string, string | readonly string[]>>
  assets?: readonly string[]
}

export const STORYBOARD: readonly StoryScene[] = [
  {
    id: 'problem',
    start: 0,
    end: 84,
    copy: {
      eyebrow: 'RFID HANDHELD SCANNERS · BLE',
      headline: 'Testing an RFID app without the scanner in your hand?',
      chips: ['Nordic ID EXA51', 'EXA81', 'BLE', 'NUR protocol'],
    },
  },
  {
    id: 'emulator',
    start: 78,
    end: 186,
    copy: {
      eyebrow: 'BUILT ON SCANNER-EMU',
      headline: 'A Nordic ID EXA scanner, emulated in Python.',
      app: 'Your app',
      link: 'BLE · Nordic UART · NUR',
      host: 'scanner-emu on macOS',
      radio: 'USB Bluetooth dongle or Android emulator',
    },
  },
  {
    id: 'store',
    start: 180,
    end: 318,
    copy: {
      callout: 'Walk a store generated from your product catalog.',
    },
    assets: ['ui/3d-store-aisle.png', 'ui/3d-store-scan-start.png'],
  },
  {
    id: 'scan',
    start: 312,
    end: 492,
    copy: {
      calloutScan: 'Aim at a shelf. Tags flow to your app over BLE.',
      calloutProgress: 'Every shelf turns green as the inventory fills.',
    },
    assets: ['ui/scan-clip.mp4'],
  },
  {
    id: 'cli',
    start: 486,
    end: 576,
    copy: {
      eyebrow: 'HEADLESS TOO',
      headline: 'Or drive it from the REPL.',
      command: '$ scanner-emu run --transport usb:0 --model exa51',
      output: [
        'BLE peripheral started name=EXA51-EMU',
        'scanner-emu> rfid queue 3034F4E4E422FB40075BCD15',
        'scanner-emu> barcode emit 4012345358216',
        'scanner-emu> trigger press',
      ],
    },
  },
  {
    id: 'closing',
    start: 570,
    end: 660,
    copy: {
      product: 'RFID Store Simulator',
      headline: 'The RFID scanner, without the scanner.',
      footer: 'Python 3.10+ · MIT · github.com/dees91/rfid-store-simulator',
    },
    assets: ['ui/3d-store-final.png'],
  },
] as const

export function getScene(id: SceneID): StoryScene {
  const scene = STORYBOARD.find((candidate) => candidate.id === id)
  if (!scene) throw new Error(`Unknown scene: ${id}`)
  return scene
}

export function sceneDuration(scene: StoryScene): number {
  return scene.end - scene.start
}

export function copyString(scene: StoryScene, key: string): string {
  const value = scene.copy[key]
  if (typeof value !== 'string') throw new Error(`Scene ${scene.id} copy ${key} is not a string`)
  return value
}

export function copyLines(scene: StoryScene, key: string): readonly string[] {
  const value = scene.copy[key]
  if (!Array.isArray(value)) throw new Error(`Scene ${scene.id} copy ${key} is not a list`)
  return value
}
