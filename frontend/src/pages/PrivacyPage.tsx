import { Card, CardContent, Link, Stack, Typography } from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

/** The privacy policy, in plain language (DPDP Act 2023 transparency duty). */
export function PrivacyPage() {
  const { t } = useTranslation()

  return (
    <Stack spacing={2}>
      <Typography variant="h2" component="h1" sx={{ color: 'darkgreen' }}>
        {t('privacy.title')}
      </Typography>
      <Typography color="text.secondary">{t('privacy.updated')}</Typography>

      <Card>
        <CardContent>
          <Stack spacing={2}>
            <Typography>{t('privacy.intro')}</Typography>
            <Typography>{t('privacy.whatWeStore')}</Typography>
            <Typography>{t('privacy.whoSeesIt')}</Typography>
            <Typography>{t('privacy.assistant')}</Typography>
            <Typography>{t('privacy.messages')}</Typography>
            <Typography>{t('privacy.retention')}</Typography>
            <Typography>{t('privacy.rights')}</Typography>
            <Link component={RouterLink} to="/settings">
              {t('settings.viewConsents')}
            </Link>
          </Stack>
        </CardContent>
      </Card>
    </Stack>
  )
}
