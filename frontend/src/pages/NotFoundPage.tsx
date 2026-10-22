import { Button, Stack, Typography } from '@mui/material'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

export function NotFoundPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  return (
    <Stack
      component="main"
      spacing={2}
      sx={{
        minHeight: '100dvh',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        p: 3,
        backgroundColor: 'mintcream',
      }}
    >
      <Typography variant="h2" component="h1" sx={{ color: 'darkgreen' }}>
        {t('errors.notFoundTitle')}
      </Typography>
      <Typography color="text.secondary">{t('errors.notFoundBody')}</Typography>
      <Button variant="contained" size="large" onClick={() => void navigate('/')}>
        {t('errors.goHome')}
      </Button>
    </Stack>
  )
}
