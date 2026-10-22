import { Navigate } from 'react-router-dom'

import { useAuth } from './context'
import { LoadingScreen } from '../components/LoadingScreen'

/** Sends the visitor to login, onboarding, or the app depending on their state. */
export function HomeRedirect() {
  const { status, profile } = useAuth()

  if (status === 'loading') return <LoadingScreen />
  if (status === 'anonymous') return <Navigate to="/login" replace />
  if (profile && !profile.profile_complete) return <Navigate to="/onboarding" replace />
  return <Navigate to="/dashboard" replace />
}
