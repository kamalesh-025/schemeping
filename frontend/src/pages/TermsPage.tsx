import { Card, CardContent, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

/** The terms of use: what SchemePing is, and what it is not. */
export function TermsPage() {
  const { t } = useTranslation()

  return (
    <Stack spacing={2}>
      <Typography variant="h2" component="h1" sx={{ color: 'darkgreen' }}>
        {t('terms.title')}
      </Typography>
      <Typography color="text.secondary">{t('terms.updated')}</Typography>

      <Card>
        <CardContent>
          <Stack spacing={2}>
            <Typography>{t('terms.service')}</Typography>
            <Typography>{t('terms.accuracy')}</Typography>
            <Typography>{t('terms.eligibility')}</Typography>
            <Typography>{t('terms.noGuarantee')}</Typography>
            <Typography>{t('terms.liability')}</Typography>
            <Typography>{t('terms.changes')}</Typography>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  )
}
