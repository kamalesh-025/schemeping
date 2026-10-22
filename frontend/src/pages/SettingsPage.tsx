import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControlLabel,
  Link,
  Snackbar,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material'
import LogoutIcon from '@mui/icons-material/Logout'
import DeleteForeverIcon from '@mui/icons-material/DeleteForever'
import DownloadIcon from '@mui/icons-material/Download'
import { Link as RouterLink } from 'react-router-dom'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { ErrorBanner } from '../components/ErrorBanner'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { useAuth } from '../auth/context'
import { ApiError } from '../api/client'
import { authApi, notificationsApi, privacyApi, profileApi } from '../api/endpoints'
import type { AuthConfig, NotificationPrefs } from '../api/types'

const CONFIRM_WORD = 'DELETE'

const CATEGORY_KEYS: { key: keyof NotificationPrefs; label: string }[] = [
  { key: 'new_schemes', label: 'settings.categoryNewSchemes' },
  { key: 'family_milestones', label: 'settings.categoryFamilyMilestones' },
  { key: 'deadlines', label: 'settings.categoryDeadlines' },
  { key: 'festival', label: 'settings.categoryFestival' },
]

export function SettingsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { profile, setProfile, logout } = useAuth()

  const [error, setError] = useState<unknown>(null)
  const [savedNote, setSavedNote] = useState(false)
  const [whatsappBusy, setWhatsappBusy] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [confirmWord, setConfirmWord] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null)
  const [prefsBusy, setPrefsBusy] = useState(false)
  const [prefsLoading, setPrefsLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exported, setExported] = useState(false)
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordBusy, setPasswordBusy] = useState(false)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [passwordSaved, setPasswordSaved] = useState(false)
  const profileId = profile?.id

  const loadConsents = useCallback(async () => {
    setError(null)
    setPrefsLoading(true)
    try {
      const record = await privacyApi.consents()
      setPrefs(record.notification_preferences)
    } catch (caught) {
      setError(caught)
    } finally {
      setPrefsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (profileId) void loadConsents()
  }, [loadConsents, profileId])

  useEffect(() => {
    let cancelled = false
    authApi
      .config()
      .then((value) => {
        if (!cancelled) setAuthConfig(value)
      })
      .catch(() => {
        // An older deployment may not expose the route; then no password card.
        if (!cancelled) setAuthConfig(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const changePassword = async (event: FormEvent) => {
    event.preventDefault()
    if (passwordBusy) return
    setPasswordError(null)

    const minimum = authConfig?.password_min_length ?? 8
    if (newPassword.length < minimum) {
      setPasswordError(t('errors.passwordTooShort', { count: minimum }))
      return
    }
    if (newPassword !== confirmPassword) {
      setPasswordError(t('errors.passwordMismatch'))
      return
    }

    setPasswordBusy(true)
    try {
      await authApi.changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setPasswordSaved(true)
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 400) {
        setPasswordError(t('errors.wrongCurrentPassword'))
      } else if (caught instanceof ApiError && caught.status === 429) {
        setPasswordError(t('errors.tooManyAttempts'))
      } else if (caught instanceof ApiError && caught.status === 0) {
        setPasswordError(t('errors.network'))
      } else {
        setPasswordError(t('errors.generic'))
      }
    } finally {
      setPasswordBusy(false)
    }
  }

  if (!profile) return null

  const lastFour = profile.mobile.slice(-4)
  const location = [profile.district, profile.state].filter(Boolean).join(', ')

  const toggleWhatsapp = async (enabled: boolean) => {
    setError(null)
    setWhatsappBusy(true)
    try {
      await profileApi.setWhatsappConsent(enabled)
      setProfile({ ...profile, consent_whatsapp: enabled })
      setSavedNote(true)
    } catch (caught) {
      setError(caught)
    } finally {
      setWhatsappBusy(false)
    }
  }

  const deleteAccount = async () => {
    setDeleting(true)
    setError(null)
    try {
      await profileApi.deleteAccount()
      await logout()
      void navigate('/login', { replace: true })
    } catch (caught) {
      setError(caught)
      setDeleting(false)
      setDeleteOpen(false)
    }
  }

  const toggleCategory = async (key: keyof NotificationPrefs, enabled: boolean) => {
    if (!prefs) return
    setPrefsBusy(true)
    setError(null)
    try {
      setPrefs(await notificationsApi.updatePreferences({ [key]: enabled }))
    } catch (caught) {
      setError(caught)
    } finally {
      setPrefsBusy(false)
    }
  }

  const exportData = async () => {
    setExporting(true)
    setError(null)
    try {
      const data = await privacyApi.exportData()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = 'schemeping-my-data.json'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
      setExported(true)
    } catch (caught) {
      setError(caught)
    } finally {
      setExporting(false)
    }
  }

  return (
    <Stack spacing={3}>
      <Box className="page-heading">
        <Typography variant="h2" component="h1" sx={{ color: 'navy' }}>
          {t('settings.title')}
        </Typography>
      </Box>
      <Typography className="settings-intro">{t('settings.subtitle')}</Typography>

      <Box className="settings-profile-summary" data-ui="profile-summary">
        <Box className="settings-profile-summary__identity">
          <Box className="settings-profile-summary__initial" aria-hidden="true">
            {(profile.name || t('settings.account')).trim().slice(0, 1).toLocaleUpperCase()}
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography component="h2" variant="h3">
              {profile.name || t('settings.account')}
            </Typography>
            <Typography component="p">
              {t('settings.mobileEnding', { lastFour })}
            </Typography>
            {location ? <Typography component="p">{location}</Typography> : null}
          </Box>
        </Box>
        <Box className="settings-profile-summary__status">
          <Typography component="p">{t('settings.profileStatus')}</Typography>
          <Chip
            color={profile.profile_complete ? 'success' : 'warning'}
            label={
              profile.profile_complete
                ? t('settings.profileReady')
                : t('settings.profileNeedsAttention')
            }
          />
        </Box>
      </Box>

      {!profile.profile_complete ? (
        <Alert
          severity="warning"
          action={
            <Button color="inherit" size="small" onClick={() => void navigate('/onboarding')}>
              {t('common.continue')}
            </Button>
          }
        >
          {t('settings.profileIncomplete')}
        </Alert>
      ) : null}

      <ErrorBanner error={error} />

      <Box className="settings-workspace">
        <Stack className="settings-primary">
          <Card className="settings-section settings-section--language">
            <CardContent>
              <Typography variant="h3" component="h2" sx={{ mb: 1 }}>
                {t('settings.language')}
              </Typography>
              <Typography color="text.secondary" sx={{ mb: 2 }}>
                {t('settings.languageHelp')}
              </Typography>
              <LanguageSwitcher />
            </CardContent>
          </Card>

          <Card className="settings-section settings-section--notifications">
            <CardContent>
              <Typography variant="h3" component="h2" sx={{ mb: 1 }}>
                {t('settings.notifications')}
              </Typography>
              <Typography color="text.secondary" sx={{ mb: 1 }}>
                {t('settings.notificationsHelp')}
              </Typography>
              {prefs ? (
                <Stack spacing={1}>
                  {CATEGORY_KEYS.map((category) => (
                    <FormControlLabel
                      key={category.key}
                      control={
                        <Switch
                          checked={prefs[category.key]}
                          onChange={(event) =>
                            void toggleCategory(category.key, event.target.checked)
                          }
                          disabled={prefsBusy}
                          inputProps={{ 'aria-label': t(category.label) }}
                        />
                      }
                      label={t(category.label)}
                    />
                  ))}
                </Stack>
              ) : (
                <Button
                  variant="outlined"
                  size="large"
                  onClick={() => void loadConsents()}
                  disabled={prefsLoading}
                >
                  {prefsLoading ? t('common.loading') : t('settings.viewConsents')}
                </Button>
              )}
            </CardContent>
          </Card>

          <Card className="settings-section settings-section--data">
            <CardContent>
              <Typography variant="h3" component="h2" sx={{ mb: 1 }}>
                {t('settings.data')}
              </Typography>
              <Typography color="text.secondary" sx={{ mb: 2 }}>
                {t('settings.dataHelp')}
              </Typography>
              <Button
                variant="outlined"
                size="large"
                startIcon={<DownloadIcon />}
                onClick={() => void exportData()}
                disabled={exporting}
              >
                {exporting ? t('privacy.downloading') : t('privacy.download')}
              </Button>
            </CardContent>
          </Card>
        </Stack>

        <Stack className="settings-secondary">
          <Card className="settings-section settings-section--whatsapp">
            <CardContent>
              <Typography variant="h3" component="h2" sx={{ mb: 1 }}>
                {t('settings.whatsapp')}
              </Typography>
              <Typography color="text.secondary" sx={{ mb: 1 }}>
                {t('settings.whatsappHelp')}
              </Typography>
              <FormControlLabel
                control={
                  <Switch
                    checked={profile.consent_whatsapp}
                    onChange={(event) => void toggleWhatsapp(event.target.checked)}
                    disabled={whatsappBusy}
                    inputProps={{ 'aria-label': t('settings.whatsapp') }}
                  />
                }
                label={
                  profile.consent_whatsapp
                    ? t('settings.whatsapp')
                    : t('common.optional')
                }
              />
            </CardContent>
          </Card>

          {authConfig?.mode === 'password' ? (
            <Card className="settings-section settings-section--password">
              <CardContent>
                <Typography variant="h3" component="h2" sx={{ mb: 1 }}>
                  {t('settings.passwordTitle')}
                </Typography>
                <Typography color="text.secondary" sx={{ mb: 2 }}>
                  {t('settings.passwordHelp')}
                </Typography>
                {passwordError ? (
                  <Alert severity="error" role="alert" sx={{ mb: 2 }}>
                    {passwordError}
                  </Alert>
                ) : null}
                <Box
                  component="form"
                  onSubmit={(event) => void changePassword(event)}
                  noValidate
                >
                  <Stack spacing={2}>
                    <TextField
                      data-ui="current-password-control"
                      label={t('settings.currentPassword')}
                      type="password"
                      value={currentPassword}
                      onChange={(event) => setCurrentPassword(event.target.value)}
                      autoComplete="current-password"
                      required
                    />
                    <TextField
                      data-ui="new-password-control"
                      label={t('settings.newPassword')}
                      type="password"
                      value={newPassword}
                      onChange={(event) => setNewPassword(event.target.value)}
                      helperText={t('login.passwordHint', {
                        count: authConfig.password_min_length,
                      })}
                      autoComplete="new-password"
                      required
                    />
                    <TextField
                      data-ui="confirm-new-password-control"
                      label={t('settings.confirmNewPassword')}
                      type="password"
                      value={confirmPassword}
                      onChange={(event) => setConfirmPassword(event.target.value)}
                      autoComplete="new-password"
                      required
                    />
                    <Button
                      type="submit"
                      variant="outlined"
                      size="large"
                      fullWidth
                      disabled={
                        passwordBusy || !currentPassword || !newPassword || !confirmPassword
                      }
                    >
                      {passwordBusy
                        ? t('settings.changingPassword')
                        : t('settings.changePassword')}
                    </Button>
                  </Stack>
                </Box>
              </CardContent>
            </Card>
          ) : null}

          <Card className="settings-section settings-section--account">
            <CardContent>
              <Typography variant="h3" component="h2" sx={{ mb: 1 }}>
                {t('settings.account')}
              </Typography>
              <Typography color="text.secondary" sx={{ mb: 2 }}>
                {t('settings.deleteAccountHelp')}
              </Typography>
              <Stack className="settings-account-actions" spacing={1.5}>
                <Button
                  variant="outlined"
                  size="large"
                  startIcon={<LogoutIcon />}
                  onClick={() => {
                    void logout().then(() => navigate('/login', { replace: true }))
                  }}
                >
                  {t('common.logout')}
                </Button>
                <Button
                  variant="contained"
                  color="error"
                  size="large"
                  startIcon={<DeleteForeverIcon />}
                  onClick={() => {
                    setConfirmWord('')
                    setDeleteOpen(true)
                  }}
                >
                  {t('settings.deleteAccount')}
                </Button>
              </Stack>
            </CardContent>
          </Card>

          <Box className="settings-privacy-note">
            <Typography component="h2" variant="h3">
              {t('settings.privacyNoteTitle')}
            </Typography>
            <Typography component="p">{t('settings.privacyNote')}</Typography>
            <Box className="settings-privacy-note__links">
              <Link component={RouterLink} to="/privacy">
                {t('settings.privacyPolicy')}
              </Link>
              <Link component={RouterLink} to="/terms">
                {t('settings.termsOfUse')}
              </Link>
            </Box>
          </Box>
        </Stack>
      </Box>

      <Dialog
        open={deleteOpen}
        onClose={deleting ? undefined : () => setDeleteOpen(false)}
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle sx={{ fontWeight: 700 }}>{t('settings.deleteConfirmTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ fontSize: '1rem', mb: 2 }}>
            {t('settings.deleteConfirmBody')}
          </DialogContentText>
          <TextField
            label={t('settings.confirmWordLabel')}
            value={confirmWord}
            onChange={(event) => setConfirmWord(event.target.value.toUpperCase())}
            autoComplete="off"
          />
        </DialogContent>
        <DialogActions sx={{ p: 2, gap: 1 }}>
          <Button onClick={() => setDeleteOpen(false)} disabled={deleting} color="inherit">
            {t('common.cancel')}
          </Button>
          <Button
            onClick={() => void deleteAccount()}
            variant="contained"
            color="error"
            disabled={deleting || confirmWord !== CONFIRM_WORD}
          >
            {deleting ? t('settings.deleting') : t('common.delete')}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={savedNote}
        autoHideDuration={1500}
        message={t('family.savedMessage')}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        onClose={() => setSavedNote(false)}
      />
      <Snackbar
        open={exported}
        autoHideDuration={2500}
        message={t('privacy.downloaded')}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        onClose={() => setExported(false)}
      />
      <Snackbar
        open={passwordSaved}
        autoHideDuration={2500}
        message={t('settings.passwordChanged')}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        onClose={() => setPasswordSaved(false)}
      />
    </Stack>
  )
}
