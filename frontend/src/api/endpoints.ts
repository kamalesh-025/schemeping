import { api } from './client'
import type {
  AnalyticsEventKind,
  AuthConfig,
  CardsResponse,
  CardsParams,
  ChatAnswer,
  ChatHistory,
  Consent,
  ConsentRecord,
  FacilitiesResponse,
  FamilyMember,
  FamilyMemberInput,
  Features,
  Language,
  Locations,
  OtpRequestResponse,
  Profile,
  ProfileUpdate,
  RecomputeReport,
  SchemeDetail,
  SchemeDetailQuery,
  SessionUser,
  SummaryResponse,
  NotificationPrefs,
} from './types'

export const authApi = {
  config: () => api.get<AuthConfig>('/auth/config'),
  register: (mobile: string, password: string) =>
    api.post<SessionUser>('/auth/register', { mobile, password }),
  login: (mobile: string, password: string) =>
    api.post<SessionUser>('/auth/login', { mobile, password }),
  changePassword: (currentPassword: string, newPassword: string) =>
    api.post<void>('/auth/password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),
  requestOtp: (mobile: string) =>
    api.post<OtpRequestResponse>('/auth/otp/request', { mobile }),
  verifyOtp: (mobile: string, otp: string) =>
    api.post<SessionUser>('/auth/otp/verify', { mobile, otp }),
  verifyWidgetOtp: (accessToken: string) =>
    api.post<SessionUser>('/auth/otp/widget/verify', { access_token: accessToken }),
  currentSession: () => api.get<SessionUser>('/auth/session'),
  logout: () => api.post<void>('/auth/logout'),
}

export const profileApi = {
  getMe: () => api.get<Profile>('/me'),
  updateMe: (payload: ProfileUpdate) => api.put<Profile>('/me', payload),
  getConsent: () => api.get<Consent>('/me/consent'),
  setWhatsappConsent: (whatsappOptIn: boolean) =>
    api.patch<Consent>('/me/consent/whatsapp', { whatsapp_opt_in: whatsappOptIn }),
  deleteAccount: () => api.delete<void>('/me', { confirm: 'DELETE' }),
}

export const familyApi = {
  list: () => api.get<FamilyMember[]>('/family'),
  create: (payload: FamilyMemberInput) => api.post<FamilyMember>('/family', payload),
  get: (id: number) => api.get<FamilyMember>(`/family/${id}`),
  update: (id: number, payload: Partial<FamilyMemberInput>) =>
    api.patch<FamilyMember>(`/family/${id}`, payload),
  remove: (id: number) => api.delete<void>(`/family/${id}`),
}

export const referenceApi = {
  locations: () => api.get<Locations>('/reference/locations'),
}

export const eligibilityApi = {
  cards: (params?: CardsParams) => api.get<CardsResponse>('/eligibility', { params }),
  summary: () => api.get<SummaryResponse>('/eligibility/summary'),
  recompute: () => api.post<RecomputeReport>('/eligibility/recompute'),
}

export const schemesApi = {
  detail: (schemeId: number, query?: SchemeDetailQuery) =>
    api.get<SchemeDetail>(`/schemes/${schemeId}`, { params: query }),
}

export const featuresApi = {
  get: () => api.get<Features>('/features'),
}

export interface WhatsAppSummaryResponse {
  status: 'queued' | 'skipped' | 'failed'
  reason: string | null
  notification_id: number | null
}

export const notificationsApi = {
  updatePreferences: (payload: Partial<NotificationPrefs>) =>
    api.patch<NotificationPrefs>('/me/notification-prefs', payload),
  sendSchemeSummary: (schemeId: number, params: { person?: string; language?: string }) =>
    api.post<WhatsAppSummaryResponse>(`/schemes/${schemeId}/send-whatsapp`, undefined, {
      params,
    }),
}

export const facilitiesApi = {
  nearest: (params: { lat: number; lon: number; type?: string; limit?: number }) =>
    api.get<FacilitiesResponse>('/facilities/nearest', { params }),
  byDistrict: (params: { district?: string; pincode?: string; limit?: number }) =>
    api.get<FacilitiesResponse>('/facilities', { params }),
}

export const chatApi = {
  ask: (message: string, language?: Language) =>
    api.post<ChatAnswer>('/chat', { message, language: language ?? null }),
  history: (limit = 50) => api.get<ChatHistory>('/chat/history', { params: { limit } }),
}

export const eventsApi = {
  track: (kind: AnalyticsEventKind, schemeId?: number) =>
    api.post<{ recorded: boolean; kind: string }>('/events', {
      kind,
      scheme_id: schemeId ?? null,
    }),
}

export const privacyApi = {
  consents: () => api.get<ConsentRecord>('/me/consents'),
  exportData: () => api.get<Record<string, unknown>>('/me/export'),
}
