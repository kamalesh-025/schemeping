import { BottomNavigation, BottomNavigationAction, Paper } from '@mui/material'
import FamilyRestroomIcon from '@mui/icons-material/FamilyRestroom'
import SettingsIcon from '@mui/icons-material/Settings'
import HomeIcon from '@mui/icons-material/Home'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

const ITEMS = [
  { path: '/dashboard', icon: <HomeIcon />, labelKey: 'nav.home' },
  { path: '/family', icon: <FamilyRestroomIcon />, labelKey: 'nav.family' },
  { path: '/settings', icon: <SettingsIcon />, labelKey: 'nav.settings' },
] as const

export function BottomNav() {
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useTranslation()

  const current = Math.max(
    0,
    ITEMS.findIndex((item) => location.pathname.startsWith(item.path)),
  )

  return (
    <Paper
      elevation={0}
      square
      className="site-bottom-nav"
      sx={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        display: { xs: 'block', md: 'none' },
        borderTop: '4px solid navy',
        zIndex: (theme) => theme.zIndex.appBar,
      }}
    >
      <BottomNavigation
        showLabels
        value={current}
        onChange={(_event, index: number) => {
          void navigate(ITEMS[index].path)
        }}
        sx={{ backgroundColor: 'white', minHeight: 64 }}
      >
        {ITEMS.map((item) => (
          <BottomNavigationAction
            key={item.path}
            label={t(item.labelKey)}
            icon={item.icon}
            sx={{ minHeight: 60, '& .MuiBottomNavigationAction-label': { fontSize: '0.9rem' } }}
          />
        ))}
      </BottomNavigation>
    </Paper>
  )
}
