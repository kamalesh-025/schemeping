import { Box, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

const MIN_SCALE = 0.8
const MAX_SCALE = 1.6

/** A- / A+ text-size control for elderly users. Applies a page-level zoom. */
export function TextSizeControl({
  scale,
  onChange,
}: {
  scale: number
  onChange: (next: number) => void
}) {
  const { t } = useTranslation()

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Typography color="text.secondary" sx={{ flexGrow: 1 }}>
        {t('detail.textSize')}
      </Typography>
      <Box
        component="button"
        type="button"
        aria-label={t('detail.textDecrease')}
        onClick={() => onChange(Math.max(MIN_SCALE, Math.round((scale - 0.1) * 10) / 10))}
        sx={{
          minWidth: 48,
          minHeight: 48,
          borderRadius: 1,
          border: '2px solid darkgreen',
          backgroundColor: 'white',
          color: 'darkgreen',
          fontSize: '1rem',
          fontWeight: 700,
          cursor: 'pointer',
        }}
      >
        A−
      </Box>
      <Box
        component="button"
        type="button"
        aria-label={t('detail.textIncrease')}
        onClick={() => onChange(Math.min(MAX_SCALE, Math.round((scale + 0.1) * 10) / 10))}
        sx={{
          minWidth: 48,
          minHeight: 48,
          borderRadius: 1,
          border: '2px solid darkgreen',
          backgroundColor: 'white',
          color: 'darkgreen',
          fontSize: '1rem',
          fontWeight: 700,
          cursor: 'pointer',
        }}
      >
        A+
      </Box>
    </Box>
  )
}
