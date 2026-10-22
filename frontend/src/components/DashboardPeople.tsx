import { Box, Chip, Stack, Typography } from '@mui/material'
import FaceIcon from '@mui/icons-material/Face'
import GroupIcon from '@mui/icons-material/Group'
import PersonIcon from '@mui/icons-material/Person'
import { useTranslation } from 'react-i18next'

import type { PersonSummary, StatusCounts } from '../api/types'

export type PersonSelection = 'me' | number

function personKey(person: PersonSummary): string {
  return person.kind === 'me' ? 'me' : String(person.id)
}

function personValue(person: PersonSummary): PersonSelection {
  return person.kind === 'me' ? 'me' : (person.id ?? 'me')
}

function personName(person: PersonSummary, t: (key: string) => string): string {
  if (person.kind === 'me') return t('dashboard.person_you')
  return person.name || t('dashboard.person_unnamed')
}

/** Chips to pick whose results are shown: the account owner or a family member. */
export function PersonSelector({
  people,
  value,
  onChange,
}: {
  people: PersonSummary[]
  value: PersonSelection
  onChange: (value: PersonSelection) => void
}) {
  const { t } = useTranslation()

  return (
    <Stack
      role="group"
      aria-label={t('dashboard.select_person')}
      direction="row"
      data-ui="person-selector"
      sx={{ flexWrap: 'wrap', gap: 1 }}
    >
      {people.map((person) => {
        const key = personKey(person)
        const selected = key === (value === 'me' ? 'me' : String(value))
        const eligible = person.counts.eligible
        const label =
          eligible > 0 ? `${personName(person, t)} (${eligible})` : personName(person, t)
        const icon =
          person.kind === 'me' ? (
            <PersonIcon fontSize="small" aria-hidden="true" />
          ) : (
            <FaceIcon fontSize="small" aria-hidden="true" />
          )

        return (
          <Chip
            key={key}
            component="button"
            type="button"
            icon={icon}
            label={label}
            color={selected ? 'primary' : 'default'}
            variant={selected ? 'filled' : 'outlined'}
            aria-pressed={selected}
            onClick={() => onChange(personValue(person))}
            sx={{ minHeight: 48, px: 1, fontSize: '1rem' }}
          />
        )
      })}
      {people.length === 1 ? (
        <Chip
          icon={<GroupIcon fontSize="small" aria-hidden="true" />}
          label={t('nav.family')}
          variant="outlined"
          sx={{ minHeight: 48, color: 'gray' }}
        />
      ) : null}
    </Stack>
  )
}

/** Three big numbers: eligible, may qualify (missing info), and schemes checked. */
export function SummaryStrip({ counts }: { counts: StatusCounts | undefined }) {
  const { t } = useTranslation()

  return (
    <Box
      data-ui="eligibility-summary"
      sx={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: 1,
        py: 2,
        px: 1.5,
        backgroundColor: 'white',
        borderRadius: 1,
        borderLeft: '4px solid darkgreen',
      }}
    >
      <Box sx={{ textAlign: 'center' }}>
        <Typography variant="h2" component="p" sx={{ color: 'seagreen', fontWeight: 700 }}>
          {counts ? counts.eligible : '–'}
        </Typography>
        <Typography color="text.secondary">{t('dashboard.count_eligible')}</Typography>
      </Box>
      <Box sx={{ textAlign: 'center' }}>
        <Typography variant="h2" component="p" sx={{ color: 'saddlebrown', fontWeight: 700 }}>
          {counts ? counts.needs_info : '–'}
        </Typography>
        <Typography color="text.secondary">{t('dashboard.count_maybe')}</Typography>
      </Box>
      <Box sx={{ textAlign: 'center' }}>
        <Typography variant="h2" component="p" sx={{ color: 'darkslategray', fontWeight: 700 }}>
          {counts ? counts.total : '–'}
        </Typography>
        <Typography color="text.secondary">{t('dashboard.count_total')}</Typography>
      </Box>
    </Box>
  )
}
