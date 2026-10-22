import { Box, CircularProgress, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

/** Loading state for the eligibility results list. */
export function SchemeCardSkeleton() {
  const { t } = useTranslation()

  return (
    <Box
      role="status"
      aria-live="polite"
      data-ui="scheme-results-loading"
      sx={{
        minHeight: 240,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 2,
        backgroundColor: 'white',
        borderLeft: '4px solid darkgreen',
      }}
    >
      <CircularProgress size={24} aria-hidden />
      <Typography>{t('common.loading')}</Typography>
    </Box>
  )
}
