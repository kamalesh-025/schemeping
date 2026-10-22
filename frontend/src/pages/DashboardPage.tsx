import { useCallback, useEffect, useMemo, useState } from 'react'
import { Box, Button, Typography } from '@mui/material'
import LogoutIcon from '@mui/icons-material/Logout'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { eligibilityApi } from '../api/endpoints'
import type { CardsResponse, SummaryResponse } from '../api/types'
import { useAuth } from '../auth/context'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState } from '../components/EmptyState'
import { ErrorBanner } from '../components/ErrorBanner'
import { FilterChips } from '../components/FilterChips'
import type { CategoryFilter, ScopeFilter } from '../components/FilterChips'
import { PersonSelector, SummaryStrip } from '../components/DashboardPeople'
import type { PersonSelection } from '../components/DashboardPeople'
import { SchemeCardSkeleton } from '../components/SchemeCardSkeleton'
import { SchemeCardItem } from '../components/SchemeCards'

const PAGE_SIZE = 20

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

export function DashboardPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { logout } = useAuth()

  const [summary, setSummary] = useState<SummaryResponse | null>(null)
  const [cards, setCards] = useState<CardsResponse | null>(null)
  const [limit, setLimit] = useState(PAGE_SIZE)
  const [person, setPerson] = useState<PersonSelection>('me')
  const [scope, setScope] = useState<ScopeFilter>('all')
  const [category, setCategory] = useState<CategoryFilter>('all')
  const [summaryError, setSummaryError] = useState<unknown>(null)
  const [cardsError, setCardsError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [logoutOpen, setLogoutOpen] = useState(false)

  const handleLogout = useCallback(async () => {
    try {
      await logout()
    } catch {
      // The local session is cleared even when the server call fails, so the
      // user still leaves the app.
    }
    await navigate('/login', { replace: true })
  }, [logout, navigate])

  const loadSummary = useCallback(async (signal: AbortSignal) => {
    setSummaryError(null)
    try {
      const data = await eligibilityApi.summary()
      if (!signal.aborted) setSummary(data)
    } catch (error) {
      if (!isAbortError(error) && !signal.aborted) setSummaryError(error)
    }
  }, [])

  const loadCards = useCallback(
    async (signal: AbortSignal, limitValue: number, personValue: PersonSelection, scopeValue: ScopeFilter, categoryValue: CategoryFilter) => {
      setCardsError(null)
      setBusy(true)
      try {
        const data = await eligibilityApi.cards({
          person: String(personValue),
          scope: scopeValue === 'all' ? undefined : scopeValue,
          category: categoryValue === 'all' ? undefined : categoryValue,
          limit: limitValue,
        })
        if (!signal.aborted) setCards(data)
      } catch (error) {
        if (!isAbortError(error) && !signal.aborted) setCardsError(error)
      } finally {
        if (!signal.aborted) setBusy(false)
      }
    },
    [],
  )

  useEffect(() => {
    const controller = new AbortController()
    void loadSummary(controller.signal)
    return () => {
      controller.abort()
    }
  }, [loadSummary])

  useEffect(() => {
    const controller = new AbortController()
    void loadCards(controller.signal, limit, person, scope, category)
    return () => {
      controller.abort()
    }
  }, [limit, person, scope, category, loadCards])

  const selectedSummary = useMemo(() => {
    if (!summary) return undefined
    if (person === 'me') return summary.people.find((entry) => entry.kind === 'me')?.counts
    return summary.people.find((entry) => entry.kind === 'family' && entry.id === person)
      ?.counts
  }, [summary, person])

  const selectedName = useMemo(() => {
    if (person === 'me' || !summary) return undefined
    return (
      summary.people.find((entry) => entry.kind === 'family' && entry.id === person)?.name ??
      undefined
    )
  }, [summary, person])

  const canLoadMore = cards ? cards.cards.length < cards.total : false

  const retry = useCallback(() => {
    const controller = new AbortController()
    void loadSummary(controller.signal)
    void loadCards(controller.signal, limit, person, scope, category)
  }, [loadSummary, loadCards, limit, person, scope, category])

  if (summaryError) {
    return <ErrorBanner error={summaryError} onRetry={retry} />
  }

  return (
    <Box sx={{ display: 'grid', gap: 3 }}>
      <Box className="page-heading page-heading--with-action">
        <Box className="page-heading__text">
          <Typography variant="h2" component="h1">
            {t('dashboard.title')}
          </Typography>
          <Typography color="text.secondary">{t('dashboard.subtitle')}</Typography>
        </Box>
        <Button
          className="page-heading__action"
          variant="outlined"
          size="large"
          startIcon={<LogoutIcon />}
          onClick={() => setLogoutOpen(true)}
        >
          {t('common.logout')}
        </Button>
      </Box>

      <Box
        className="dashboard-workspace"
        sx={{
          display: 'grid',
          gap: 3,
          gridTemplateColumns: { xs: '1fr', md: 'minmax(250px, 0.34fr) minmax(0, 1fr)' },
        }}
      >
        <Box data-ui="dashboard-controls" sx={{ display: 'grid', alignContent: 'start', gap: 2.5 }}>
          <PersonSelector
            people={summary?.people ?? []}
            value={person}
            onChange={(next) => {
              setLimit(PAGE_SIZE)
              setPerson(next)
            }}
          />

          <SummaryStrip counts={selectedSummary} />

          <FilterChips
            scope={scope}
            category={category}
            onScope={(next) => {
              setLimit(PAGE_SIZE)
              setScope(next)
            }}
            onCategory={(next) => {
              setLimit(PAGE_SIZE)
              setCategory(next)
            }}
          />
        </Box>

        <Box component="section" className="dashboard-results" aria-label={t('dashboard.title')}>
          {cardsError ? <ErrorBanner error={cardsError} onRetry={retry} /> : null}

          {busy && !cards ? <SchemeCardSkeleton /> : null}

          {!busy && !cardsError ? (
            cards && cards.cards.length > 0 ? (
              <Box className="scheme-results-grid">
                {cards.cards.map((card) => (
                  <SchemeCardItem
                    key={card.scheme_id}
                    card={card}
                    selected={person}
                    selectedName={selectedName}
                  />
                ))}
                {canLoadMore ? (
                  <Box
                    component="button"
                    type="button"
                    onClick={() => setLimit((current) => current + PAGE_SIZE)}
                    sx={{
                      gridColumn: '1 / -1',
                      minHeight: 48,
                      borderRadius: 1,
                      border: '2px solid darkgreen',
                      backgroundColor: 'white',
                      color: 'darkgreen',
                      fontSize: '1rem',
                      fontWeight: 650,
                      cursor: 'pointer',
                    }}
                  >
                    {t('dashboard.show_more')}
                  </Box>
                ) : null}
              </Box>
            ) : (
              <EmptyState
                title={t('dashboard.empty_title')}
                hint={busy ? undefined : t('dashboard.empty_hint')}
              />
            )
          ) : null}
        </Box>
      </Box>

      <ConfirmDialog
        open={logoutOpen}
        title={t('dashboard.logoutTitle')}
        body={t('dashboard.logoutBody')}
        confirmLabel={t('common.logout')}
        onConfirm={handleLogout}
        onClose={() => setLogoutOpen(false)}
      />
    </Box>
  )
}
