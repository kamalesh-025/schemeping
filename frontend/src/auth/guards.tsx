import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from './context'
import { LoadingScreen } from '../components/LoadingScreen'

/** Unauthenticated users are sent to the login screen. */
export function RequireAuth() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') return <LoadingScreen />
  if (status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <Outlet />
}

/** A signed-in user with an unfinished profile is routed to onboarding. */
export function RequireCompleteProfile() {
  const { profile } = useAuth()

  if (profile && !profile.profile_complete) {
    return <Navigate to="/onboarding" replace />
  }
  return <Outlet />
}
