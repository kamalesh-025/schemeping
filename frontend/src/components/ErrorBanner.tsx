import { Alert, Button } from '@mui/material'
import { useTranslation } from 'react-i18next'

import { messageForError } from '../api/errors'

export function ErrorBanner({
  error,
  onRetry,
}: {
  error: unknown
  onRetry?: () => void
}) {
  const { t } = useTranslation()
  if (!error) return null

  const raw = messageForError(error)
  const isKey = raw.startsWith('errors.')
  const text = isKey ? t(raw) : raw

  return (
    <Alert
      severity="error"
      role="alert"
      action={
        onRetry ? (
          <Button color="inherit" size="small" onClick={onRetry}>
            {t('common.retry')}
          </Button>
        ) : undefined
      }
    >
      {text}
    </Alert>
  )
}
