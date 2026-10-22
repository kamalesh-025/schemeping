import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import i18n, { persistLanguage, type LanguageCode } from '../i18n'
import { ApiError, setUnauthorizedHandler } from '../api/client'
import { authApi, profileApi } from '../api/endpoints'
import type { Profile } from '../api/types'
import { AuthContext, type AuthContextValue, type AuthStatus } from './context'

const SUPPORTED: LanguageCode[] = ['en', 'ta', 'hi']

function syncLanguage(language: string): void {
  if (SUPPORTED.includes(language as LanguageCode)) {
    const code = language as LanguageCode
    if (i18n.language !== code) {
      void i18n.changeLanguage(code)
    }
    persistLanguage(code)
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [profile, setProfileState] = useState<Profile | null>(null)

  const reload = useCallback(async () => {
    try {
      const me = await profileApi.getMe()
      setProfileState(me)
      setStatus('authenticated')
      syncLanguage(me.language)
    } catch (error) {
      setProfileState(null)
      setStatus('anonymous')
      if (!(error instanceof ApiError)) throw error
    }
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setProfileState(null)
      setStatus('anonymous')
    })
    void reload()
  }, [reload])

  const setProfile = useCallback((next: Profile) => {
    setProfileState(next)
    setStatus('authenticated')
  }, [])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      setProfileState(null)
      setStatus('anonymous')
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ status, profile, reload, setProfile, logout }),
    [status, profile, reload, setProfile, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
