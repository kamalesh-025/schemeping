import { Box, Typography } from '@mui/material'
import { NavLink, Link as RouterLink, Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { BottomNav } from './BottomNav'
import { ChatPanel } from './ChatPanel'
import { LanguageSwitcher } from './LanguageSwitcher'

export function AppShell() {
  const { t } = useTranslation()
  const navigation = [
    { to: '/dashboard', label: t('nav.home') },
    { to: '/family', label: t('nav.family') },
    { to: '/settings', label: t('nav.settings') },
  ]

  return (
    <Box className="site-shell">
      <Box className="site-topline">
        <Box className="site-topline__inner">
          <Typography component="p">{t('common.independentTag')}</Typography>
        </Box>
      </Box>
      <Box component="header" className="site-header">
        <Box className="site-header__inner">
          <Box
            component={RouterLink}
            to="/dashboard"
            className="site-brand"
            aria-label={t('common.appName')}
          >
            <Box
              component="img"
              src="/icons/schemeping_logo-320.png"
              alt=""
              className="site-brand__logo"
            />
            <Box className="site-brand__copy">
              <Typography component="span" className="site-brand__name">
                {t('common.appName')}
              </Typography>
              <Typography component="span" className="site-brand__descriptor">
                {t('common.serviceDescriptor')}
              </Typography>
            </Box>
          </Box>
          <Box className="site-header__tools">
            <LanguageSwitcher compact />
          </Box>
        </Box>
      </Box>

      <Box
        component="nav"
        className="site-nav site-nav--desktop"
        aria-label={t('common.mainNavigation')}
      >
        <Box className="site-nav__inner">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/dashboard'}
              className="site-nav__link"
            >
              {item.label}
            </NavLink>
          ))}
        </Box>
      </Box>

      <Box component="main" className="site-content page-enter">
        <Box className="site-content__inner">
          <Outlet />
        </Box>
      </Box>

      <Box component="footer" className="site-footer">
        <Box className="site-footer__inner">
          <Typography component="p" className="site-footer__disclaimer">
            {t('common.serviceDisclaimer')}
          </Typography>
          <Box className="site-footer__links">
            <RouterLink to="/privacy">{t('settings.privacyPolicy')}</RouterLink>
            <RouterLink to="/terms">{t('settings.termsOfUse')}</RouterLink>
          </Box>
        </Box>
      </Box>
      <BottomNav />
      <ChatPanel />
    </Box>
  )
}
