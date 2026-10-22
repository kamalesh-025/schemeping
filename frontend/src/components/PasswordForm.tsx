import { useState, type FormEvent } from 'react'
import {
  Box,
  Button,
  IconButton,
  InputAdornment,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material'
import Visibility from '@mui/icons-material/Visibility'
import VisibilityOff from '@mui/icons-material/VisibilityOff'
import { useTranslation } from 'react-i18next'

import { ErrorBanner } from './ErrorBanner'
import { ApiError } from '../api/client'
import { authApi } from '../api/endpoints'
import { useAuth } from '../auth/context'

const MOBILE_PATTERN = /^[6-9]\d{9}$/

type Mode = 'signin' | 'signup'

/** Turn server status codes into messages the user can read in their language. */
function friendlyError(caught: unknown): unknown {
  if (!(caught instanceof ApiError)) return caught
  if (caught.status === 0) return new ApiError(0, 'errors.network')
  if (caught.status === 401) return new ApiError(401, 'errors.invalidCredentials')
  if (caught.status === 409) return new ApiError(409, 'errors.accountExists')
  if (caught.status === 429) return new ApiError(429, 'errors.tooManyAttempts')
  if (caught.status === 400 || caught.status === 422) {
    return new ApiError(caught.status, 'errors.checkFields')
  }
  return caught
}

/**
 * Mobile number + password sign-in and sign-up.
 *
 * No SMS is sent. The same number and password are used every time, which keeps
 * the flow usable without a DLT-registered sender.
 */
export function PasswordForm({ minLength }: { minLength: number }) {
  const { t } = useTranslation()
  const { reload } = useAuth()

  const [mode, setMode] = useState<Mode>('signin')
  const [mobile, setMobile] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)

  const mobileValid = MOBILE_PATTERN.test(mobile)
  const passwordValid = password.length >= minLength
  const confirmValid = mode === 'signin' || confirm === password
  const canSubmit = mobileValid && passwordValid && confirmValid

  const switchMode = (next: Mode) => {
    setMode(next)
    setPassword('')
    setConfirm('')
    setError(null)
    setSubmitted(false)
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setSubmitted(true)
    if (!canSubmit || busy) return

    setError(null)
    setBusy(true)
    try {
      if (mode === 'signup') {
        await authApi.register(mobile, password)
      } else {
        await authApi.login(mobile, password)
      }
      // The provider loads the session and routes to onboarding or dashboard.
      await reload()
    } catch (caught) {
      setError(friendlyError(caught))
      setBusy(false)
    }
  }

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h2" component="h1" sx={{ color: 'darkgreen' }}>
          {t('login.title')}
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 1 }}>
          {t('login.passwordSubtitle')}
        </Typography>
      </Box>

      <Tabs
        value={mode}
        onChange={(_event, value: Mode) => switchMode(value)}
        variant="fullWidth"
        aria-label={t('login.modeLabel')}
        sx={{ minHeight: 48 }}
      >
        <Tab value="signin" label={t('login.signInTab')} sx={{ minHeight: 48 }} />
        <Tab value="signup" label={t('login.createAccountTab')} sx={{ minHeight: 48 }} />
      </Tabs>

      <ErrorBanner error={error} />

      <Box component="form" onSubmit={submit} noValidate>
        <Stack spacing={2}>
          <TextField
            data-ui="mobile-number-control"
            label={t('login.mobileLabel')}
            placeholder={t('login.mobilePlaceholder')}
            value={mobile}
            onChange={(event) => setMobile(event.target.value.replace(/\D/g, '').slice(0, 10))}
            error={submitted && !mobileValid}
            helperText={
              submitted && !mobileValid ? t('login.mobilePlaceholder') : ' '
            }
            autoComplete="tel-national"
            inputProps={{ inputMode: 'numeric' }}
            required
          />

          <TextField
            data-ui="password-control"
            label={t('login.passwordLabel')}
            type={showPassword ? 'text' : 'password'}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            error={submitted && !passwordValid}
            helperText={t('login.passwordHint', { count: minLength })}
            autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
            required
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    aria-label={
                      showPassword ? t('login.hidePassword') : t('login.showPassword')
                    }
                    onClick={() => setShowPassword((value) => !value)}
                    edge="end"
                    sx={{ width: 48, height: 48 }}
                  >
                    {showPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />

          {mode === 'signup' && (
            <TextField
              data-ui="confirm-password-control"
              label={t('login.confirmPasswordLabel')}
              type={showPassword ? 'text' : 'password'}
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              error={submitted && !confirmValid}
              helperText={submitted && !confirmValid ? t('login.passwordMismatch') : ' '}
              autoComplete="new-password"
              required
            />
          )}

          <Typography variant="body2" color="text.secondary">
            {mode === 'signup' ? t('login.noOtpNote') : t('login.forgotPasswordHelp')}
          </Typography>

          <Button
            data-ui="submit-password-control"
            type="submit"
            variant="contained"
            size="large"
            fullWidth
            disabled={busy}
          >
            {busy
              ? t(mode === 'signin' ? 'login.signingIn' : 'login.creatingAccount')
              : t(mode === 'signin' ? 'login.signInButton' : 'login.createAccountButton')}
          </Button>
        </Stack>
      </Box>
    </Stack>
  )
}
