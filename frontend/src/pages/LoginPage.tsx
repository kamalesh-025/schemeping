import { useCallback, useEffect, useState } from 'react'
import { Box, Card, CardContent, Typography } from '@mui/material'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { ErrorBanner } from '../components/ErrorBanner'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { OtpLoginForm } from '../components/OtpLoginForm'
import { PasswordForm } from '../components/PasswordForm'
import { useAuth } from '../auth/context'
import { authApi } from '../api/endpoints'
import type { AuthConfig } from '../api/types'

/**
 * Sign-in entry point.
 *
 * The backend decides the flow: password (the default) or OTP (server-sent or
 * MSG91 widget). The page must not guess before the config call answers,
 * because rendering the wrong form wastes the user's time and trust.
 */
export function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { status, profile } = useAuth()

  const [config, setConfig] = useState<AuthConfig | null>(null)
  const [configError, setConfigError] = useState<unknown>(null)

  useEffect(() => {
    if (status === 'authenticated' && profile) {
      void navigate(profile.profile_complete ? '/dashboard' : '/onboarding', { replace: true })
    }
  }, [status, profile, navigate])

  const loadConfig = useCallback(async () => {
    setConfigError(null)
    try {
      setConfig(await authApi.config())
    } catch (caught) {
      setConfigError(caught)
    }
  }, [])

  useEffect(() => {
    void loadConfig()
  }, [loadConfig])

  const widget =
    config?.widget_id && config.widget_token
      ? { id: config.widget_id, token: config.widget_token }
      : null

  return (
    <Box component="main" className="login-layout">
      <Box component="section" className="login-intro">
        <Box component="header" className="login-intro__header">
          <Box className="login-intro__identity">
            <Box
              component="img"
              src="/icons/schemeping_logo-320.png"
              alt=""
              className="login-intro__logo"
            />
            <Typography component="h2" className="login-intro__name">
              {t('common.appName')}
            </Typography>
          </Box>
          <LanguageSwitcher compact />
        </Box>
        <Typography component="p" className="login-intro__description">
          {t('common.serviceDescriptor')}
        </Typography>
        <Typography component="p" className="login-intro__disclaimer">
          {t('common.serviceDisclaimer')}
        </Typography>
      </Box>

      <Card className="login-card" data-ui="sign-in-form">
        <CardContent sx={{ p: 3 }}>
          {configError ? (
            <ErrorBanner error={configError} onRetry={() => void loadConfig()} />
          ) : null}

          {!config && !configError ? (
            <Typography role="status">{t('common.loading')}</Typography>
          ) : null}

          {config?.mode === 'password' ? (
            <PasswordForm minLength={config.password_min_length} />
          ) : null}

          {config && config.mode !== 'password' ? (
            <OtpLoginForm widgetMode={config.mode === 'widget'} widget={widget} />
          ) : null}
        </CardContent>
      </Card>
    </Box>
  )
}
