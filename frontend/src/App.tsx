import { Route, Routes } from 'react-router-dom'

import { HomeRedirect } from './auth/HomeRedirect'
import { RequireAuth, RequireCompleteProfile } from './auth/guards'
import { AppShell } from './components/AppShell'
import { FamilyMemberPage } from './pages/FamilyMemberPage'
import { FamilyPage } from './pages/FamilyPage'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { OnboardingPage } from './pages/OnboardingPage'
import { SchemeDetailPage } from './pages/SchemeDetailPage'
import { HowToApplyPage } from './pages/HowToApplyPage'
import { PrivacyPage } from './pages/PrivacyPage'
import { TermsPage } from './pages/TermsPage'
import { SettingsPage } from './pages/SettingsPage'

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route path="/onboarding" element={<OnboardingPage />} />

        <Route element={<RequireCompleteProfile />}>
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/schemes/:schemeId" element={<SchemeDetailPage />} />
            <Route path="/schemes/:schemeId/apply" element={<HowToApplyPage />} />
            <Route path="/family" element={<FamilyPage />} />
            <Route path="/family/new" element={<FamilyMemberPage />} />
            <Route path="/family/:id/edit" element={<FamilyMemberPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/terms" element={<TermsPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="/" element={<HomeRedirect />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
