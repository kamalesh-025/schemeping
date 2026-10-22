/** API response shapes mirroring the FastAPI Pydantic schemas. */

export type Language = 'en' | 'ta' | 'hi' | 'te' | 'kn' | 'ml'
export type Gender = 'female' | 'male' | 'other' | 'prefer_not_to_say'
export type Relationship =
  | 'spouse'
  | 'son'
  | 'daughter'
  | 'father'
  | 'mother'
  | 'brother'
  | 'sister'
  | 'grandfather'
  | 'grandmother'
  | 'other'

export type EducationLevel =
  | 'no_formal'
  | 'primary'
  | 'secondary'
  | 'higher_secondary'
  | 'iti'
  | 'diploma'
  | 'undergraduate'
  | 'postgraduate'
  | 'other'

export type MaritalStatus =
  | 'single'
  | 'married'
  | 'widowed'
  | 'divorced'
  | 'separated'

export interface SessionUser {
  id: number
  name: string | null
  mobile: string
  language: Language
  profile_complete: boolean
  has_consent: boolean
}

export interface OtpRequestResponse {
  message: string
  expires_in_seconds: number
  resend_after_seconds: number
}

/** Which sign-in flow the backend wants the client to render. */
export interface AuthConfig {
  mode: 'password' | 'server' | 'widget'
  password_min_length: number
  widget_id: string | null
  widget_token: string | null
}

/** Runtime capability flags: which actions can actually work here. */
export interface Features {
  whatsapp_delivery: boolean
  whatsapp_click_to_chat: boolean
}

export interface Profile {
  id: number
  mobile: string
  name: string | null
  dob: string | null
  gender: Gender | null
  occupation: string | null
  annual_income: number | null
  is_disabled: boolean | null
  education: EducationLevel | null
  marital_status: MaritalStatus | null
  state: string | null
  district: string | null
  locality: string | null
  pincode: string | null
  language: Language
  consent_data_processing: boolean
  consent_whatsapp: boolean
  consent_version: string | null
  consented_at: string | null
  whatsapp_opted_out_at: string | null
  profile_complete: boolean
  age: number | null
  is_senior: boolean
  created_at: string
}

export interface ProfileUpdate {
  name: string
  dob: string
  gender: Gender
  occupation?: string | null
  annual_income: number
  is_disabled?: boolean
  education?: EducationLevel | null
  marital_status?: MaritalStatus | null
  state: string
  district: string
  locality?: string | null
  pincode: string
  language: Language
  data_processing_consent?: boolean
  whatsapp_opt_in?: boolean
}

export interface Consent {
  data_processing: boolean
  whatsapp_opt_in: boolean
  consented_at: string | null
  whatsapp_opted_out_at: string | null
  policy_version: string | null
}

export interface FamilyMember {
  id: number
  name: string
  relationship: Relationship
  dob: string | null
  gender: Gender | null
  occupation: string | null
  education_status: EducationLevel | null
  annual_income: number | null
  is_disabled: boolean | null
  is_student: boolean
  is_widow: boolean
  age: number | null
  is_senior: boolean
  is_minor: boolean
  created_at: string
  updated_at: string
}

export interface FamilyMemberInput {
  name: string
  relationship: Relationship
  dob?: string | null
  gender?: Gender | null
  occupation?: string | null
  education_status?: EducationLevel | null
  annual_income?: number | null
  is_disabled?: boolean
  is_student?: boolean
  is_widow?: boolean
}

export interface Locations {
  states: string[]
  districts_by_state: Record<string, string[]>
}

export type EligibilityStatus = 'eligible' | 'needs_info' | 'not_eligible'
export type SchemeScope = 'individual' | 'family'
export type CardPriority = 'high' | 'medium' | 'normal'
export type SchemeStatus = 'draft' | 'published' | 'archived'

export interface SchemeCard {
  scheme_id: number
  slug: string
  name: string
  scope: SchemeScope
  category: string
  level: string
  state: string | null
  department: string
  benefit_summary: string
  benefit_amount: string | null
  benefit_type: string
  priority: CardPriority
  status: EligibilityStatus
  reason_line: string
  missing_fields: string[]
  deadline: string | null
  days_remaining: number | null
  last_verified_on: string
}

export interface StatusCounts {
  eligible: number
  needs_info: number
  not_eligible: number
  total: number
}

export interface PersonSummary {
  kind: 'me' | 'family'
  id: number | null
  name: string | null
  counts: StatusCounts
  by_category: Record<string, StatusCounts>
}

export interface CardsResponse {
  total: number
  cards: SchemeCard[]
}

export interface SummaryResponse {
  people: PersonSummary[]
}

export type CardsParams = {
  person?: string
  category?: string
  scope?: SchemeScope | 'all'
  status?: EligibilityStatus
  limit?: number
  offset?: number
}

export interface RecomputeReport {
  people: number
  schemes: number
  created: number
  updated: number
  unchanged: number
}

export interface TranslationInfo {
  simple_title: string
  simple_description: string
  simple_benefits: string[]
  simple_steps: string[]
  cached: boolean
  fallback: boolean
}

export interface DocumentStep {
  name: string
  notes: string | null
}

export interface ApplicationStep {
  title: string
  detail: string | null
}

export type SchemeLanguage = 'en' | 'ta' | 'hi' | 'te' | 'kn' | 'ml'

export interface SchemeDetail {
  id: number
  slug: string
  name: string
  department: string
  level: 'central' | 'state'
  state: string | null
  category: string
  scope: 'individual' | 'family'
  benefit_summary: string
  benefit_amount: string | null
  benefit_type: string
  deadline: string | null
  days_remaining: number | null
  apply_url: string | null
  source_url: string
  last_verified_on: string | null
  required_documents: DocumentStep[]
  application_steps: ApplicationStep[]
  eligibility_status: EligibilityStatus
  why_qualify: string[]
  missing_fields: string[]
  person: string | number
  language: SchemeLanguage
  translation: TranslationInfo | null
}

export interface Facility {
  id: number
  name: string
  type: 'csc' | 'taluk_office' | 'collector_office' | 'e_sevai' | 'welfare_office'
  address: string
  district: string
  state: string
  pincode: string | null
  phone: string | null
  working_hours: string | null
  lat: number | null
  lon: number | null
  distance_km: number | null
}

export interface FacilitiesResponse {
  total: number
  facilities: Facility[]
}

export type SchemeDetailQuery = { lang?: SchemeLanguage; person?: string }

// ---------------------------------------------------------------- Phase 6

export interface ChatSource {
  id: number
  name: string
}

export interface ChatAnswer {
  answer: string
  sources: ChatSource[]
  language: Language
  grounded: boolean
}

export interface ChatHistoryItem {
  id: number
  role: 'user' | 'assistant'
  content: string
  language: Language
  created_at: string
}

export interface ChatHistory {
  total: number
  messages: ChatHistoryItem[]
}

export interface NotificationPrefs {
  new_schemes: boolean
  family_milestones: boolean
  deadlines: boolean
  festival: boolean
}

export interface ConsentRecord {
  data_processing: boolean
  whatsapp: boolean
  policy_version: string | null
  consented_at: string | null
  whatsapp_opted_out_at: string | null
  notification_preferences: NotificationPrefs
}

export type AnalyticsEventKind =
  | 'scheme_view'
  | 'apply_click'
  | 'whatsapp_send'
  | 'chat_question'
