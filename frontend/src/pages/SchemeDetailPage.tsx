import { useEffect, useState } from 'react'
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Container,
  FormControlLabel,
  FormGroup,
  Stack,
  Typography,
} from '@mui/material'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline'
import HighlightOffIcon from '@mui/icons-material/HighlightOff'
import { eventsApi, featuresApi, notificationsApi, schemesApi } from '../api/endpoints'
import type { SchemeDetail, SchemeLanguage } from '../api/types'
import { TextSizeControl } from '../components/TextSizeControl'
import { useTranslation } from 'react-i18next'

const LANGUAGES: { code: SchemeLanguage; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'ta', label: 'தமிழ்' },
  { code: 'hi', label: 'हिन्दी' },
  { code: 'te', label: 'తెలుగు' },
  { code: 'kn', label: 'ಕನ್ನಡ' },
  { code: 'ml', label: 'മലയാളം' },
]

/** Scheme detail: simple explanation, why-you-qualify, documents, deadline. */
export function SchemeDetailPage() {
  const { schemeId } = useParams()
  const [searchParams] = useSearchParams()
  const { t, i18n } = useTranslation()

  const person = searchParams.get('person') ?? undefined
  const [lang, setLang] = useState<SchemeLanguage>(
    (['en', 'ta', 'hi', 'te', 'kn', 'ml'] as SchemeLanguage[]).includes(
      i18n.language as SchemeLanguage
    )
      ? (i18n.language as SchemeLanguage)
      : 'en'
  )
  const [textScale, setTextScale] = useState(1)
  const [detail, setDetail] = useState<SchemeDetail | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [whatsappBusy, setWhatsappBusy] = useState(false)
  const [whatsappDelivery, setWhatsappDelivery] = useState(false)
  const [whatsappState, setWhatsappState] = useState<
    'queued' | 'needs_optin' | 'skipped' | 'error' | null
  >(null)

  useEffect(() => {
    // Only offer the server-side send when a real WhatsApp provider is
    // configured; otherwise the honest action is the free wa.me link.
    let cancelled = false
    featuresApi
      .get()
      .then((features) => {
        if (!cancelled) setWhatsappDelivery(features.whatsapp_delivery)
      })
      .catch(() => {
        if (!cancelled) setWhatsappDelivery(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setDetail(null)
    setError(false)
    setLoading(true)
    schemesApi
      .detail(Number(schemeId), { lang, person })
      .then((data) => {
        if (!controller.signal.aborted) {
          setDetail(data)
          setChecked({})
          setLoading(false)
          // Lightweight analytics: which schemes people open.
          // Never let tracking break the page.
          void eventsApi.track('scheme_view', Number(schemeId)).catch(() => undefined)
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setError(true)
          setLoading(false)
        }
      })
    return () => controller.abort()
  }, [schemeId, lang, person])

  if (schemeId === undefined) {
    return (
      <Container maxWidth="md" sx={{ py: 4 }}>
        <Alert severity="error">{t('detail.loadError')}</Alert>
      </Container>
    )
  }

  if (loading) {
    return (
      <Container maxWidth="md" sx={{ py: 6, display: 'flex', justifyContent: 'center' }}>
        <CircularProgress aria-label={t('common.loading')} />
      </Container>
    )
  }

  if (error || detail === null) {
    return (
      <Container maxWidth="md" sx={{ py: 4 }}>
        <Alert severity="error">{t('detail.loadError')}</Alert>
        <Button component={RouterLink} to="/dashboard" sx={{ minHeight: 48, color: 'darkgreen' }}>
          {t('detail.backToDashboard')}
        </Button>
      </Container>
    )
  }

  const translated = detail.translation !== null && !detail.translation.fallback
  const title = translated ? detail.translation!.simple_title : detail.name
  const description = translated ? detail.translation!.simple_description : detail.benefit_summary
  const benefits = translated ? detail.translation!.simple_benefits : [detail.benefit_summary]

  const daysRemaining = detail.days_remaining
  const deadlineUrgency =
    detail.deadline === null || daysRemaining === null
      ? 'none'
      : daysRemaining < 0
        ? 'expired'
        : daysRemaining <= 14
          ? 'soon'
          : 'ok'
  const urgencyColour =
    deadlineUrgency === 'expired'
      ? 'firebrick'
      : deadlineUrgency === 'soon'
        ? 'saddlebrown'
        : 'darkgreen'
  const notEligible = detail.eligibility_status === 'not_eligible'
  const documentNames = detail.required_documents.map((document) => document.name)
  const shareText = [
    title,
    description,
    ...benefits,
    documentNames.length > 0
      ? `${t('detail.documents')}: ${documentNames.join(', ')}`
      : null,
    detail.deadline ? `${t('detail.deadline')}: ${detail.deadline}` : null,
    detail.why_qualify[0] ?? null,
    `${t('detail.source')}: ${detail.source_url}`,
  ]
    .filter(Boolean)
    .join('\n')
  const shareUrl = `https://wa.me/?text=${encodeURIComponent(shareText)}`

  const sendWhatsAppSummary = async () => {
    setWhatsappBusy(true)
    setWhatsappState(null)
    try {
      const response = await notificationsApi.sendSchemeSummary(detail.id, { person, language: lang })
      if (response.status === 'queued') {
        setWhatsappState('queued')
      } else if (response.reason === 'not_opted_in') {
        setWhatsappState('needs_optin')
      } else {
        setWhatsappState('skipped')
      }
    } catch {
      setWhatsappState('error')
    } finally {
      setWhatsappBusy(false)
    }
  }

  return (
    <Container
      maxWidth="md"
      sx={{ py: 3, fontSize: `${16 * textScale}px` }}
      data-testid="scheme-detail"
      data-ui="scheme-detail"
    >
      <Stack spacing={3}>
        <Box className="page-heading">
          <Typography variant="h2" component="h1" fontWeight={700}>
            {title}
          </Typography>
          <Typography color="text.secondary">
            {detail.department},{' '}
            {detail.level === 'central' ? t('detail.central') : t('detail.state')},{' '}
            {t(`categories.${detail.category}`)}
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, mt: 1, flexWrap: 'wrap' }}>
            <Chip
              size="small"
              sx={
                detail.eligibility_status === 'eligible'
                  ? { backgroundColor: 'seagreen', color: 'white' }
                  : detail.eligibility_status === 'needs_info'
                    ? { backgroundColor: 'saddlebrown', color: 'white' }
                    : { backgroundColor: 'mintcream', color: 'darkgreen' }
              }
              label={t(`status.${detail.eligibility_status}`)}
            />
            {deadlineUrgency !== 'none' && daysRemaining !== null ? (
              <Chip
                size="small"
                sx={{
                  backgroundColor: deadlineUrgency === 'ok' ? 'honeydew' : urgencyColour,
                  color: deadlineUrgency === 'ok' ? 'darkgreen' : 'white',
                }}
                label={
                  daysRemaining < 0
                    ? t('detail.expired')
                    : t('detail.daysLeft', { count: daysRemaining })
                }
              />
            ) : null}
          </Box>
        </Box>

        <Box>
          <Typography variant="subtitle1" fontWeight={700}>
            {t('detail.what')}
          </Typography>
          <Typography>{description}</Typography>
        </Box>

        <Box>
          <Typography variant="subtitle1" fontWeight={700}>
            {t('detail.benefits')}
          </Typography>
          <Stack component="ul" spacing={1} sx={{ pl: 2, m: 0 }}>
            {benefits.map((benefit, index) => (
              <Typography component="li" key={`${benefit}-${index}`}>
                {benefit}
              </Typography>
            ))}
          </Stack>
          {detail.benefit_amount ? (
            <Typography color="text.secondary">{detail.benefit_amount}</Typography>
          ) : null}
        </Box>

        <Box>
          <Typography variant="subtitle1" fontWeight={700}>
            {notEligible ? t('detail.whyNot') : t('detail.whyQualify')}
          </Typography>
          {detail.why_qualify.length === 0 ? (
            <Typography color="text.secondary">{t('detail.noReasons')}</Typography>
          ) : (
            <Stack spacing={1}>
              {detail.why_qualify.map((fact, index) => (
                <Box key={`${fact}-${index}`} sx={{ display: 'flex', gap: 1 }}>
                  <Typography
                    component="span"
                    sx={{ color: notEligible ? 'firebrick' : 'forestgreen', display: 'inline-flex' }}
                    aria-hidden
                  >
                    {notEligible ? (
                      <HighlightOffIcon fontSize="small" />
                    ) : (
                      <CheckCircleOutlineIcon fontSize="small" />
                    )}
                  </Typography>
                  <Typography>{fact}</Typography>
                </Box>
              ))}
            </Stack>
          )}
        </Box>

        <Box>
          <Typography variant="subtitle1" fontWeight={700}>
            {t('detail.documents')}
          </Typography>
          {detail.required_documents.length === 0 ? (
            <Typography color="text.secondary">{t('detail.noDocuments')}</Typography>
          ) : (
            <FormGroup>
              {detail.required_documents.map((documentStep, index) => (
                <FormControlLabel
                  key={documentStep.name}
                  data-testid={`doc-check-${index}`}
                  control={
                    <Checkbox
                      checked={checked[documentStep.name] ?? false}
                      onChange={(event) =>
                        setChecked((previous) => ({
                          ...previous,
                          [documentStep.name]: event.target.checked,
                        }))
                      }
                      sx={{ '& .MuiSvgIcon-root': { fontSize: 28 } }}
                    />
                  }
                  label={<Typography>{documentStep.name}</Typography>}
                />
              ))}
            </FormGroup>
          )}
        </Box>

        {detail.deadline ? (
          <Box>
            <Typography variant="subtitle1" fontWeight={700}>
              {t('detail.deadline')}
            </Typography>
            <Typography sx={{ color: urgencyColour }}>
              {new Date(detail.deadline).toLocaleDateString(undefined, {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
              })}
            </Typography>
          </Box>
        ) : null}
        {detail.last_verified_on ? (
          <Typography color="text.secondary">
            {t('detail.verifiedOn', { date: detail.last_verified_on })}
          </Typography>
        ) : null}
        <Button
          component="a"
          href={detail.source_url}
          target="_blank"
          rel="noreferrer"
          sx={{ color: 'darkgreen', textAlign: 'left', justifyContent: 'flex-start', px: 0 }}
        >
          {t('detail.source')}
        </Button>

        <Stack spacing={2}>
          <Button
            component={RouterLink}
            to={`/schemes/${detail.id}/apply${person ? `?person=${person}&lang=${lang}` : `?lang=${lang}`}`}
            variant="contained"
            size="large"
            sx={{ minHeight: 56, fontSize: `${16 * textScale}px` }}
          >
            {t('detail.howToApply')}
          </Button>
          {whatsappDelivery ? (
            <>
              <Button
                variant="contained"
                size="large"
                sx={{ minHeight: 56 }}
                onClick={() => void sendWhatsAppSummary()}
                disabled={whatsappBusy}
              >
                {whatsappBusy ? t('detail.whatsappSending') : t('detail.sendWhatsapp')}
              </Button>
              <Button
                component="a"
                href={shareUrl}
                target="_blank"
                rel="noreferrer"
                variant="outlined"
                size="large"
                sx={{ minHeight: 56, color: 'darkgreen', borderColor: 'darkgreen' }}
              >
                {t('detail.shareWhatsapp')}
              </Button>
            </>
          ) : (
            <>
              <Button
                component="a"
                href={shareUrl}
                target="_blank"
                rel="noreferrer"
                variant="contained"
                size="large"
                sx={{ minHeight: 56 }}
                data-ui="whatsapp-share-link"
              >
                {t('detail.openWhatsapp')}
              </Button>
              <Typography variant="body2" color="text.secondary">
                {t('detail.openWhatsappHelp')}
              </Typography>
            </>
          )}
          {whatsappState ? (
            <Alert
              severity={
                whatsappState === 'queued'
                  ? 'success'
                  : whatsappState === 'needs_optin'
                    ? 'info'
                    : whatsappState === 'error'
                      ? 'error'
                      : 'warning'
              }
              role="status"
            >
              {whatsappState === 'queued'
                ? t('detail.whatsappQueued')
                : whatsappState === 'needs_optin'
                  ? t('detail.whatsappNeedsOptin')
                  : whatsappState === 'error'
                    ? t('detail.whatsappError')
                    : t('detail.whatsappSkipped')}
              {whatsappState === 'needs_optin' ? (
                <>
                  {' '}
                  <Button component={RouterLink} to="/settings" size="small" color="inherit">
                    {t('nav.settings')}
                  </Button>
                </>
              ) : null}
            </Alert>
          ) : null}
        </Stack>

        <TextSizeControl scale={textScale} onChange={setTextScale} />

        <Box>
          <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
            {t('detail.language')}
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            {LANGUAGES.map((language) => (
              <Button
                key={language.code}
                variant={language.code === lang ? 'contained' : 'outlined'}
                onClick={() => setLang(language.code)}
                sx={
                  language.code === lang
                    ? undefined
                    : { color: 'darkgreen', borderColor: 'darkgreen', minHeight: 44 }
                }
              >
                {language.label}
              </Button>
            ))}
          </Box>
          {detail.translation?.cached ? (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              {t('detail.translatedCached')}
            </Typography>
          ) : null}
        </Box>
      </Stack>
    </Container>
  )
}
