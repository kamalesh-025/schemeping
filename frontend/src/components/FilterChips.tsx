import { Box, Chip, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

export type ScopeFilter = 'all' | 'individual' | 'family'
export type CategoryFilter =
  | 'all'
  | 'education'
  | 'healthcare'
  | 'agriculture'
  | 'housing'

const SCOPES: Array<{ value: ScopeFilter; labelKey: string }> = [
  { value: 'all', labelKey: 'dashboard.filter_all' },
  { value: 'individual', labelKey: 'dashboard.filter_individual' },
  { value: 'family', labelKey: 'dashboard.filter_family' },
]

const CATEGORIES: Array<{ value: CategoryFilter; labelKey: string }> = [
  { value: 'all', labelKey: 'dashboard.filter_all' },
  { value: 'education', labelKey: 'dashboard.category_education' },
  { value: 'healthcare', labelKey: 'dashboard.category_healthcare' },
  { value: 'agriculture', labelKey: 'dashboard.category_agriculture' },
  { value: 'housing', labelKey: 'dashboard.category_housing' },
]

function ChipRow({ children }: { children: React.ReactNode }) {
  return (
    <Box data-ui="scheme-filter" sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
      {children}
    </Box>
  )
}

function FilterHead({ labelKey }: { labelKey: string }) {
  const { t } = useTranslation()
  return (
    <Typography
      variant="subtitle2"
      color="text.primary"
      sx={{ width: '100%', fontSize: '1rem', fontWeight: 700 }}
    >
      {t(labelKey)}
    </Typography>
  )
}

/** Scope and category chip filters (single-select each). */
export function FilterChips({
  scope,
  category,
  onScope,
  onCategory,
}: {
  scope: ScopeFilter
  category: CategoryFilter
  onScope: (value: ScopeFilter) => void
  onCategory: (value: CategoryFilter) => void
}) {
  const { t } = useTranslation()

  return (
    <Box sx={{ display: 'grid', gap: 2.5 }}>
      <ChipRow>
        <FilterHead labelKey="dashboard.filter_kind" />
        {SCOPES.map((item) => (
          <Chip
            key={item.value}
            component="button"
            type="button"
            label={t(item.labelKey)}
            color={scope === item.value ? 'primary' : 'default'}
            variant={scope === item.value ? 'filled' : 'outlined'}
            aria-pressed={scope === item.value}
            onClick={() => onScope(item.value)}
            sx={{ minHeight: 48, fontSize: '0.95rem', flexShrink: 0 }}
          />
        ))}
      </ChipRow>
      <ChipRow>
        <FilterHead labelKey="dashboard.filter_area" />
        {CATEGORIES.map((item) => (
          <Chip
            key={item.value}
            component="button"
            type="button"
            label={t(item.labelKey)}
            color={category === item.value ? 'primary' : 'default'}
            variant={category === item.value ? 'filled' : 'outlined'}
            aria-pressed={category === item.value}
            onClick={() => onCategory(item.value)}
            sx={{ minHeight: 48, fontSize: '0.95rem', flexShrink: 0 }}
          />
        ))}
      </ChipRow>
    </Box>
  )
}
