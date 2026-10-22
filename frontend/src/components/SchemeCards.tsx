import { Box, Button, Chip, Typography } from '@mui/material'
import AccessTimeIcon from '@mui/icons-material/AccessTime'
import EventBusyIcon from '@mui/icons-material/EventBusy'
import { useTranslation } from 'react-i18next'
import { Link as RouterLink, useNavigate } from 'react-router-dom'

import type { EligibilityStatus, SchemeCard } from '../api/types'
import type { PersonSelection } from './DashboardPeople'

const STATUS_COLOR: Record<EligibilityStatus, 'success' | 'warning' | 'default'> = {
  eligible: 'success',
  needs_info: 'warning',
  not_eligible: 'default',
}

function deadlineLine(
  card: SchemeCard,
  t: (key: string, options?: Record<string, unknown>) => string,
): string | null {
  if (!card.deadline || card.days_remaining === null) return null
  if (card.days_remaining < 0) return t('dashboard.deadline_passed')
  const days = t('dashboard.deadline_days', { count: card.days_remaining })
  return t('dashboard.deadline_left', { date: card.deadline, days })
}

/** One scheme result: name, benefit, why-you-qualify line, deadline. Tapping opens the detail page. */
export function SchemeCardItem({
  card,
  selected,
  selectedName,
}: {
  card: SchemeCard
  selected: PersonSelection
  selectedName?: string
}) {
  const { t, i18n } = useTranslation()
  const deadline = deadlineLine(card, t)
  const benefit = card.benefit_amount ?? null
  const urgent = card.priority === 'high' && card.status !== 'not_eligible'
  const personParam = selected === 'me' ? 'me' : String(selected)

  return (
    <Box
      component="article"
      data-testid="scheme-card"
      data-ui="scheme-result"
      className="scheme-result"
      sx={{
        p: 2,
        backgroundColor: 'white',
        borderRadius: 1,
        borderLeft: '4px solid darkgreen',
        display: 'grid',
        gap: 1,
        alignContent: 'start',
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <Typography
          variant="h3"
          component={RouterLink}
          to={`/schemes/${card.scheme_id}?person=${personParam}&lang=${i18n.language}`}
          sx={{
            flexGrow: 1,
            color: 'darkgreen',
            textDecoration: 'none',
            '&:hover': { color: 'midnightblue', textDecoration: 'underline' },
          }}
        >
          {card.name}
        </Typography>
        {urgent ? (
          <Chip label={t('dashboard.priority_high')} size="small" sx={{ color: 'firebrick', borderColor: 'firebrick' }} variant="outlined" />
        ) : null}
      </Box>

      {benefit ? (
        <Typography variant="body1" fontWeight={600}>
          {benefit}
        </Typography>
      ) : null}

      <Chip
        label={t(`dashboard.status_${card.status}`)}
        color={STATUS_COLOR[card.status]}
        size="small"
        sx={{ alignSelf: 'flex-start', minHeight: 32 }}
      />

      <Typography variant="body2">{card.reason_line}</Typography>

      {card.missing_fields.length > 0 && card.status === 'needs_info' ? (
        <MissingInfoCard personId={selected} memberName={selectedName} fields={card.missing_fields} />
      ) : null}

      <Typography variant="caption" color="text.secondary">
        {card.department ? `${card.department}, ` : ''}
        {card.level === 'central'
          ? t('dashboard.level_central')
          : t('dashboard.level_state')}
      </Typography>

      {deadline ? (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {card.days_remaining !== null && card.days_remaining < 0 ? (
            <EventBusyIcon fontSize="small" sx={{ color: 'firebrick' }} aria-hidden="true" />
          ) : (
            <AccessTimeIcon fontSize="small" sx={{ color: 'seagreen' }} aria-hidden="true" />
          )}
          <Typography variant="body2" sx={{ color: card.days_remaining !== null && card.days_remaining < 0 ? 'firebrick' : 'seagreen' }}>
            {deadline}
          </Typography>
        </Box>
      ) : null}
    </Box>
  )
}

/**
 * Tell the user which profile details are missing, with a shortcut to fix
 * their own profile or the family member's form.
 */
export function MissingInfoCard({
  personId,
  memberName,
  fields,
  compact,
}: {
  personId: 'me' | number
  memberName?: string
  fields: string[]
  compact?: boolean
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const fixLabel = personId === 'me' ? t('dashboard.fix_mine') : t('dashboard.fix_member', { name: memberName ?? '' })

  return (
    <Box
      sx={{
        p: 1.5,
        borderRadius: 2,
        backgroundColor: 'honeydew',
        display: 'grid',
        gap: 1,
      }}
    >
      {!compact ? (
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {t('dashboard.missing_title')}
        </Typography>
      ) : null}
      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
        {fields.map((field) => (
          <Chip
            key={field}
            label={t(`fieldLabels.${field}`, { defaultValue: field })}
            size="small"
            sx={{ backgroundColor: 'palegreen', color: 'darkslategray' }}
          />
        ))}
      </Box>
      <Button
        variant="contained"
        color="primary"
        onClick={(event) => {
          event.stopPropagation()
          navigate(personId === 'me' ? '/onboarding' : `/family/${personId}/edit`)
        }}
        sx={{ minHeight: 48 }}
      >
        {fixLabel}
      </Button>
    </Box>
  )
}
