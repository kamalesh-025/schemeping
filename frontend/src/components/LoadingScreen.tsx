import { Box, CircularProgress, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

export function LoadingScreen() {
  const { t } = useTranslation()
  return (
    <Box
      role="status"
      aria-live="polite"
      sx={{
        minHeight: '60vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 2,
      }}
    >
      <CircularProgress aria-hidden />
      <Typography color="text.secondary">{t('common.loading')}</Typography>
    </Box>
  )
}
