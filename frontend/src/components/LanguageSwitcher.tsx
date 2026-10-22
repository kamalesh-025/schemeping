import { MenuItem, Select, type SelectChangeEvent } from '@mui/material'
import { useTranslation } from 'react-i18next'

import { SUPPORTED_LANGUAGES, persistLanguage, type LanguageCode } from '../i18n'
import { profileApi } from '../api/endpoints'
import { useAuth } from '../auth/context'

/**
 * Language switcher. Changes the UI immediately and, when signed in, saves the
 * choice to the profile so messages use the same language.
 */
export function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const { i18n } = useTranslation()
  const { profile, setProfile } = useAuth()

  const handleChange = async (event: SelectChangeEvent<string>) => {
    const code = event.target.value as LanguageCode
    await i18n.changeLanguage(code)
    persistLanguage(code)
    if (profile && profile.profile_complete) {
      try {
        const updated = await profileApi.updateMe({
          ...toProfileUpdate(profile),
          language: code,
        })
        setProfile(updated)
      } catch {
        // Language already changed locally; a failed sync is not fatal.
      }
    }
  }

  return (
    <Select
      data-ui="language-control"
      value={SUPPORTED_LANGUAGES.some((item) => item.code === i18n.language) ? i18n.language : 'en'}
      onChange={handleChange}
      size="small"
      inputProps={{ 'aria-label': 'Language' }}
      sx={{
        minWidth: compact ? 120 : 160,
        backgroundColor: 'white',
        color: 'darkgreen',
        fontWeight: 600,
      }}
    >
      {SUPPORTED_LANGUAGES.map((language) => (
        <MenuItem key={language.code} value={language.code}>
          {language.nativeName}
        </MenuItem>
      ))}
    </Select>
  )
}

function toProfileUpdate(profile: {
  name: string | null
  dob: string | null
  gender: ProfileGender
  occupation: string | null
  annual_income: number | null
  education: EducationValue
  marital_status: MaritalValue
  state: string | null
  district: string | null
  locality: string | null
  pincode: string | null
  language: string
}) {
  return {
    name: profile.name ?? '',
    dob: profile.dob ?? '',
    gender: profile.gender ?? 'prefer_not_to_say',
    occupation: profile.occupation,
    annual_income: profile.annual_income ?? 0,
    education: profile.education,
    marital_status: profile.marital_status,
    state: profile.state ?? '',
    district: profile.district ?? '',
    locality: profile.locality,
    pincode: profile.pincode ?? '',
    language: profile.language,
  }
}

type ProfileGender = 'female' | 'male' | 'other' | 'prefer_not_to_say' | null
type EducationValue =
  | 'no_formal'
  | 'primary'
  | 'secondary'
  | 'higher_secondary'
  | 'iti'
  | 'diploma'
  | 'undergraduate'
  | 'postgraduate'
  | 'other'
  | null
type MaritalValue = 'single' | 'married' | 'widowed' | 'divorced' | 'separated' | null
