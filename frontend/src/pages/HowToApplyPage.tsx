import { useEffect, useState } from 'react'
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom'
import { Alert, Box, Button, Container, Stack, Typography } from '@mui/material'
import { eventsApi, schemesApi } from '../api/endpoints'
import type { SchemeDetail, SchemeLanguage } from '../api/types'
import { useAuth } from '../auth/context'
import { FacilityFinder } from '../components/FacilityFinder'
import { TextSizeControl } from '../components/TextSizeControl'
import { useTranslation } from 'react-i18next'

const FALLBACK_STEPS = [
  'apply.stepCollect',
  'apply.stepVisit',
  'apply.stepFill',
  'apply.stepSubmit',
  'apply.stepTrack',
] as const

interface StepRow {
  title: string
  detail: string | null
}

/** Step-by-step application guide plus nearest facilities. */
export function HowToApplyPage() {
  const { schemeId } = useParams()
  const [searchParams] = useSearchParams()
  const { profile } = useAuth()
  const { t } = useTranslation()
  const [textScale, setTextScale] = useState(1)
  const [detail, setDetail] = useState<SchemeDetail | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)

  const person = searchParams.get('person') ?? undefined
  const lang = (searchParams.get('lang') as SchemeLanguage | null) ?? undefined

  useEffect(() => {
    if (schemeId === undefined) return
    const controller = new AbortController()
    setError(false)
    setLoading(true)
    schemesApi
      .detail(Number(schemeId), { lang, person })
      .then((data) => {
        if (!controller.signal.aborted) {
          setDetail(data)
          setLoading(false)
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
        <Alert severity="error">{t('apply.loadError')}</Alert>
      </Container>
    )
  }

  const steps: StepRow[] =
    detail && detail.application_steps.length > 0
      ? detail.application_steps.map((step) => ({ title: step.title, detail: step.detail }))
      : FALLBACK_STEPS.map((key) => ({ title: t(key), detail: null }))

  return (
    <Container
      maxWidth="md"
      sx={{ py: 3, fontSize: `${16 * textScale}px` }}
      data-testid="how-to-apply"
      data-ui="application-guide"
    >
      <Button
        component={RouterLink}
        to={`/schemes/${schemeId}${person || lang ? `?${buildQuery(person, lang)}` : ''}`}
        sx={{ minHeight: 48, color: 'darkgreen', mb: 2 }}
      >
        {t('common.back')}
      </Button>

      {error ? <Alert severity="error">{t('apply.loadError')}</Alert> : null}

      {detail ? (
        <Box className="page-heading">
          <Typography variant="h2" component="h1" fontWeight={700}>
            {detail.translation && !detail.translation.fallback
              ? detail.translation.simple_title
              : detail.name}
          </Typography>
        </Box>
      ) : null}

      <Stack spacing={2} sx={{ mb: 3 }}>
        {steps.map((step, index) => (
          <Box
            key={`${step.title}-${index}`}
            data-ui="application-step"
            sx={{
              borderLeft: '4px solid darkgreen',
              borderRadius: 1,
              p: 2,
              backgroundColor: 'white',
            }}
          >
            <Typography fontWeight={700}>
              {index + 1}. {step.title}
            </Typography>
            {step.detail ? <Typography>{step.detail}</Typography> : null}
          </Box>
        ))}
        <Button
          variant="contained"
          size="large"
          href={detail?.apply_url ?? undefined}
          disabled={!detail?.apply_url}
          onClick={() => {
            // Analytics must never block the application link.
            void eventsApi.track('apply_click', Number(schemeId)).catch(() => undefined)
          }}
          sx={{ minHeight: 56, fontSize: `${16 * textScale}px` }}
        >
          {t('apply.startOnline')}
        </Button>
      </Stack>

      {detail ? (
        <Box sx={{ mb: 3 }}>
          <Typography variant="h6" fontWeight={700} sx={{ mb: 1 }}>
            {t('detail.documents')}
          </Typography>
          {(detail.required_documents.length
            ? detail.required_documents
            : [{ name: t('apply.bringDocuments'), notes: null }]
          ).map((documentStep) => (
            <Typography key={documentStep.name}>• {documentStep.name}</Typography>
          ))}
        </Box>
      ) : null}

      <Box sx={{ mb: 3 }}>
        <TextSizeControl scale={textScale} onChange={setTextScale} />
      </Box>

      {loading ? null : (
        <Box>
          <Typography variant="h6" fontWeight={700} sx={{ mb: 1 }}>
            {t('apply.nearest')}
          </Typography>
          <FacilityFinder district={profile?.district ?? undefined} />
        </Box>
      )}
    </Container>
  )
}

function buildQuery(person?: string, lang?: SchemeLanguage): string {
  const params = new URLSearchParams()
  if (person !== undefined && person !== '') params.set('person', person)
  if (lang !== undefined) params.set('lang', lang)
  return params.toString()
}
