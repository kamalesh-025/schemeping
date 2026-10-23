import '@testing-library/jest-dom/vitest'
import { configure } from '@testing-library/react'
import { createRequire } from 'node:module'

import * as colorManipulatorShim from './src/theme/colorManipulator'

/**
 * These are full-app integration tests in jsdom: MUI, routing, and two or three
 * sequential API calls before the first screen settles. The 1s default for
 * `findBy*` is too tight on a loaded CI or developer machine, and it fails as a
 * misleading "element not found" instead of a slow test.
 */
configure({ asyncUtilTimeout: 5000 })

/**
 * jsdom does not implement matchMedia, which MUI's responsive helpers use.
 */
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}

/**
 * The app theme uses CSS colour names, which MUI's own colour helpers cannot
 * parse. In the browser build a Vite alias swaps MUI's colorManipulator for our
 * colour-name-aware shim, but Vitest loads MUI from node_modules as externalised
 * CommonJS, which bypasses bundler aliases. Those modules read their helpers off
 * the shared CJS exports object at call time, so replacing the exports here makes
 * the tests exercise the same behaviour as the app.
 */
function installColorNameHelpers(): void {
  const require = createRequire(import.meta.url)
  let realExports: Record<string, unknown>
  try {
    realExports = require('@mui/system/colorManipulator/colorManipulator.js') as Record<
      string,
      unknown
    >
  } catch {
    return
  }
  for (const [name, implementation] of Object.entries(colorManipulatorShim)) {
    if (name === 'default' || typeof implementation !== 'function') continue
    realExports[name] = implementation
  }
}

installColorNameHelpers()
