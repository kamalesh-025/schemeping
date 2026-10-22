import { Box, Typography } from '@mui/material'

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string
  hint?: string
  action?: { label: string; onClick: () => void }
}) {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: 1.25,
        textAlign: 'left',
        py: 4,
        px: 3,
        backgroundColor: 'white',
        borderLeft: '4px solid darkgreen',
        borderRadius: 1,
      }}
    >
      <Typography variant="h3" component="p">
        {title}
      </Typography>
      {hint ? <Typography color="text.secondary">{hint}</Typography> : null}
      {action ? (
        <Box
          component="button"
          type="button"
          onClick={action.onClick}
          sx={{
            mt: 1,
            minHeight: 48,
            px: 3,
            borderRadius: 1,
            border: 'none',
            backgroundColor: 'darkgreen',
            color: 'white',
            fontSize: '1.0625rem',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          {action.label}
        </Box>
      ) : null}
    </Box>
  )
}
