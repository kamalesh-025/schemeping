import { defineConfig, loadEnv, type UserConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import type { InlineConfig } from 'vitest/node'

// MUI's colour helpers (alpha/lighten/darken) only understand hex/rgb/hsl
// values, but this project uses CSS colour names deliberately. The alias swaps
// MUI's colorManipulator for a colour-name-aware implementation built on CSS
// color-mix(), so the theme stays free of hex codes.
const colorNameHelpers = fileURLToPath(new URL('./src/theme/colorManipulator.ts', import.meta.url))

const testConfig: InlineConfig = {
  globals: true,
  environment: 'jsdom',
  setupFiles: ['./vitest.setup.ts'],
  css: false,
  // These are integration tests: a full app render, MUI, and character-by-
  // character typing into controlled fields. 5s (the default) is too tight on
  // a loaded CI or developer machine.
  testTimeout: 20000,
}

type ConfigWithTest = UserConfig & { test: InlineConfig }

const DEFAULT_API_TARGET = 'http://127.0.0.1:8000'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_TARGET || DEFAULT_API_TARGET
  const devPort = env.VITE_DEV_PORT ? Number(env.VITE_DEV_PORT) : 5173

  const config: ConfigWithTest = {
    plugins: [react()],
    resolve: {
      alias: [
        {
          find: /^@mui\/system\/colorManipulator(\.js)?$/,
          replacement: colorNameHelpers,
        },
        {
          find: /^@mui\/system\/(?:esm|modern)\/colorManipulator\/colorManipulator\.js$/,
          replacement: colorNameHelpers,
        },
      ],
    },
    optimizeDeps: {
      esbuildOptions: {
        plugins: [
          {
            name: 'schemeping-mui-color-manipulator',
            setup(build) {
              build.onResolve(
                { filter: /^@mui\/system\/colorManipulator(?:\.js)?$/ },
                () => ({ path: colorNameHelpers }),
              )
              build.onResolve(
                {
                  filter:
                    /^@mui\/system\/(?:esm|modern)\/colorManipulator\/colorManipulator\.js$/,
                },
                () => ({ path: colorNameHelpers }),
              )
              build.onResolve({ filter: /^\.\/colorManipulator(?:\.js)?$/ }, (args) => {
                if (
                  args.importer.replaceAll('\\', '/').includes('/@mui/system/esm/colorManipulator/')
                ) {
                  return { path: colorNameHelpers }
                }
                return undefined
              })
            },
          },
        ],
      },
    },
    server: {
      port: devPort,
      proxy: {
        // Same-origin in development so httpOnly session cookies work without
        // any CORS or cookie-domain configuration.
        '/api': { target: apiTarget, changeOrigin: false },
        '/health': { target: apiTarget, changeOrigin: false },
      },
    },
    build: {
      rollupOptions: {
        output: {
          // Keep vendor code in separate, cacheable chunks; the app shell stays
          // small so the PWA loads fast on a slow mobile connection.
          manualChunks: {
            react: ['react', 'react-dom', 'react-router-dom'],
            mui: ['@mui/material', '@mui/system', '@emotion/react', '@emotion/styled'],
            i18n: ['i18next', 'react-i18next'],
          },
        },
      },
    },
    test: testConfig,
  }

  return config
})
