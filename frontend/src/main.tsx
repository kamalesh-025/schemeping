import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import CssBaseline from '@mui/material/CssBaseline'
import { ThemeProvider } from '@mui/material/styles'
import * as Sentry from '@sentry/react'

import { App } from './App'
import { AuthProvider } from './auth/AuthContext'
import { theme } from './theme/theme'
import './theme/global.css'
import './i18n'

// Error monitoring: only active when a DSN is configured (VITE_SENTRY_DSN).
// No personal data is attached (sendDefaultPii is off by default).
const sentryDsn = import.meta.env.VITE_SENTRY_DSN
if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    environment: import.meta.env.MODE,
    // No personal data is attached (Sentry's PII sending stays off).
    tracesSampleRate: 0,
  })
}

const container = document.getElementById('root')
if (!container) {
  throw new Error('Root container not found')
}

createRoot(container).render(
  <StrictMode>
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
)

if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    void navigator.serviceWorker.register('/sw.js').catch(() => undefined)
  })
}
