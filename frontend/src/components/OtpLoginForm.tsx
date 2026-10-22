import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Box, Button, Stack, TextField, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

import { ErrorBanner } from './ErrorBanner'
import { ApiError } from '../api/client'
import { authApi } from '../api/endpoints'
import { useAuth } from '../auth/context'
import {
  WIDGET_CAPTCHA_ELEMENT_ID,
  loadMsg91Widget,
  sendWidgetOtp,
  verifyWidgetOtp,
} from '../auth/msg91Widget'

const MOBILE_PATTERN = /^[6-9]\d{9}$/

/**
 * The OTP sign-in flow (AUTH_MODE=otp).
 *
 * Two deliveries are supported: the backend sends and verifies the code
 * (``server``), or MSG91's widget does it in the browser (``widget``) and the
 * backend only exchanges its access token for a session.
 */
export function OtpLoginForm({
  widgetMode,
  widget,
}: {
  widgetMode: boolean
  widget: { id: string; token: string } | null
}) {
  const { t } = useTranslation()
  const { reload } = useAuth()

  const [step, setStep] = useState<'mobile' | 'otp'>('mobile')
  const [mobile, setMobile] = useState('')
  const [otp, setOtp] = useState('')
  // A widget deployment without credentials must say so instead of quietly
  // falling back to a backend flow that is not configured.
  const [error, setError] = useState<unknown>(
    widgetMode && !widget ? new ApiError(400, 'errors.otpWidgetUnavailable') : null,
  )
  const [mobileError, setMobileError] = useState(false)
  const [busy, setBusy] = useState(false)
  const [secondsLeft, setSecondsLeft] = useState(0)
  const [widgetReady, setWidgetReady] = useState(false)

  useEffect(() => {
    if (!widget) return
    let cancelled = false
    loadMsg91Widget(widget.id, widget.token)
      .then(() => {
        if (!cancelled) setWidgetReady(true)
      })
      .catch(() => {
        if (!cancelled) setError(new ApiError(400, 'errors.otpWidgetUnavailable'))
      })
    return () => {
      cancelled = true
    }
  }, [widget])

  useEffect(() => {
    if (secondsLeft <= 0) return
    const timer = window.setInterval(() => {
      setSecondsLeft((value) => (value <= 1 ? 0 : value - 1))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [secondsLeft])

  const mobileValid = useMemo(() => MOBILE_PATTERN.test(mobile), [mobile])

  const sendOtp = async () => {
    setError(null)
    if (!mobileValid) {
      setMobileError(true)
      return
    }
    setMobileError(false)
    if (widgetMode && (!widget || !widgetReady)) {
      setError(new ApiError(400, 'errors.otpWidgetUnavailable'))
      return
    }
    setBusy(true)
    try {
      if (widgetMode) {
        await sendWidgetOtp(mobile)
        setSecondsLeft(60)
      } else {
        const result = await authApi.requestOtp(mobile)
        setSecondsLeft(result.resend_after_seconds)
      }
      setStep('otp')
    } catch (caught) {
      setError(caught)
    } finally {
      setBusy(false)
    }
  }

  const verifyOtp = async () => {
    setError(null)
    setBusy(true)
    try {
      if (widgetMode) {
        // MSG91 verifies the code; the backend turns its token into a session.
        const accessToken = await verifyWidgetOtp(otp)
        await authApi.verifyWidgetOtp(accessToken)
      } else {
        await authApi.verifyOtp(mobile, otp)
      }
      await reload()
    } catch (caught) {
      setError(caught)
      setBusy(false)
    }
  }

  const onMobileSubmit = (event: FormEvent) => {
    event.preventDefault()
    void sendOtp()
  }

  const onOtpSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (otp.length === 6) void verifyOtp()
  }

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h2" component="h1" sx={{ color: 'darkgreen' }}>
          {step === 'mobile' ? t('login.title') : t('login.otpTitle')}
        </Typography>
        <Typography color="text.secondary" sx={{ mt: 1 }}>
          {step === 'mobile'
            ? t('login.subtitle')
            : t('login.otpSubtitle', { mobile: `+91 ${mobile}` })}
        </Typography>
      </Box>

      <ErrorBanner error={error} />

      {step === 'mobile' ? (
        <Box component="form" onSubmit={onMobileSubmit} noValidate>
          <TextField
            data-ui="mobile-number-control"
            label={t('login.mobileLabel')}
            placeholder={t('login.mobilePlaceholder')}
            value={mobile}
            onChange={(event) => setMobile(event.target.value.replace(/\D/g, '').slice(0, 10))}
            error={mobileError}
            helperText={mobileError ? t('login.mobilePlaceholder') : ' '}
            autoComplete="tel-national"
            inputProps={{ inputMode: 'numeric' }}
            required
          />
          <Typography
            data-ui="development-otp-instructions"
            variant="body2"
            color="text.secondary"
            sx={{ mt: 2 }}
          >
            {widgetMode ? t('login.widgetHint') : t('login.devHint')}
          </Typography>
          <Button
            data-ui="request-otp-control"
            type="submit"
            variant="contained"
            size="large"
            fullWidth
            disabled={busy || !mobileValid || (widgetMode && !widgetReady)}
          >
            {busy ? t('login.sending') : t('login.sendOtp')}
          </Button>
        </Box>
      ) : (
        <Box component="form" onSubmit={onOtpSubmit} noValidate>
          {!widgetMode && (
            <Typography data-ui="otp-instructions" variant="body2" color="text.secondary">
              {t('login.devHint')}
            </Typography>
          )}
          <TextField
            data-ui="otp-code-control"
            label={t('login.otpLabel')}
            value={otp}
            onChange={(event) => setOtp(event.target.value.replace(/\D/g, '').slice(0, 6))}
            autoComplete="one-time-code"
            inputProps={{
              inputMode: 'numeric',
              style: { letterSpacing: '0.5rem', fontSize: '1.5rem' },
            }}
            required
          />
          <Button
            data-ui="verify-otp-control"
            type="submit"
            variant="contained"
            size="large"
            fullWidth
            disabled={busy || otp.length !== 6}
          >
            {busy ? t('login.verifying') : t('login.verify')}
          </Button>
          <Stack direction="row" spacing={1} sx={{ mt: 2, alignItems: 'center' }}>
            <Button onClick={() => void sendOtp()} disabled={busy || secondsLeft > 0} color="secondary">
              {secondsLeft > 0 ? t('login.resendIn', { seconds: secondsLeft }) : t('login.resend')}
            </Button>
            <Button
              onClick={() => {
                setStep('mobile')
                setOtp('')
                setError(null)
              }}
              color="inherit"
            >
              {t('login.changeNumber')}
            </Button>
          </Stack>
        </Box>
      )}

      {widgetMode && (
        // reCAPTCHA is rendered by the MSG91 SDK into this node when the
        // widget has captcha validation enabled.
        <Box id={WIDGET_CAPTCHA_ELEMENT_ID} data-ui="otp-widget-captcha" sx={{ minHeight: 1 }} />
      )}
    </Stack>
  )
}
