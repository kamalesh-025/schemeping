import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Step,
  StepLabel,
  Stepper,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { ErrorBanner } from '../components/ErrorBanner'
import { LoadingScreen } from '../components/LoadingScreen'
import { useAuth } from '../auth/context'
import { profileApi, referenceApi } from '../api/endpoints'
import type { EducationLevel, Gender, Locations, MaritalStatus, ProfileUpdate } from '../api/types'
import { SUPPORTED_LANGUAGES, persistLanguage, type LanguageCode } from '../i18n'

const TOTAL_STEPS = 3

const GENDERS: Gender[] = ['female', 'male', 'other', 'prefer_not_to_say']
const EDUCATIONS: EducationLevel[] = [
  'no_formal',
  'primary',
  'secondary',
  'higher_secondary',
  'iti',
  'diploma',
  'undergraduate',
  'postgraduate',
  'other',
]
const MARITAL: MaritalStatus[] = ['single', 'married', 'widowed', 'divorced', 'separated']

const GENDER_KEYS: Record<Gender, string> = {
  female: 'onboarding.genderFemale',
  male: 'onboarding.genderMale',
  other: 'onboarding.genderOther',
  prefer_not_to_say: 'onboarding.genderPreferNotToSay',
}
const EDUCATION_KEYS: Record<EducationLevel, string> = {
  no_formal: 'onboarding.educationNoFormal',
  primary: 'onboarding.educationPrimary',
  secondary: 'onboarding.educationSecondary',
  higher_secondary: 'onboarding.educationHigherSecondary',
  iti: 'onboarding.educationIti',
  diploma: 'onboarding.educationDiploma',
  undergraduate: 'onboarding.educationUndergraduate',
  postgraduate: 'onboarding.educationPostgraduate',
  other: 'onboarding.educationOther',
}
const MARITAL_KEYS: Record<MaritalStatus, string> = {
  single: 'onboarding.maritalSingle',
  married: 'onboarding.maritalMarried',
  widowed: 'onboarding.maritalWidowed',
  divorced: 'onboarding.maritalDivorced',
  separated: 'onboarding.maritalSeparated',
}

interface FormState {
  name: string
  dob: string
  gender: Gender | ''
  occupation: string
  annual_income: string
  is_disabled: boolean
  education: EducationLevel | ''
  marital_status: MaritalStatus | ''
  state: string
  district: string
  locality: string
  pincode: string
  language: LanguageCode
  consentData: boolean
  consentWhatsapp: boolean
}

function initialForm(language: string, consentData: boolean, consentWhatsapp: boolean): FormState {
  const supported = SUPPORTED_LANGUAGES.some((item) => item.code === language)
  return {
    name: '',
    dob: '',
    gender: '',
    occupation: '',
    annual_income: '',
    is_disabled: false,
    education: '',
    marital_status: '',
    state: '',
    district: '',
    locality: '',
    pincode: '',
    language: supported ? (language as LanguageCode) : 'en',
    consentData,
    consentWhatsapp,
  }
}

export function OnboardingPage() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const { profile, setProfile } = useAuth()

  const [form, setForm] = useState<FormState>(() =>
    initialForm(
      profile?.language ?? 'en',
      profile?.consent_data_processing ?? false,
      profile?.consent_whatsapp ?? false,
    ),
  )
  const [step, setStep] = useState(0)
  const [error, setError] = useState<unknown>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [locations, setLocations] = useState<Locations | null>(null)

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((current) => ({ ...current, [key]: value }))

  useEffect(() => {
    if (profile && profile.name && form.name === '') {
      setForm((current) => ({
        ...current,
        name: profile.name ?? '',
        dob: profile.dob ?? '',
        gender: profile.gender ?? '',
        occupation: profile.occupation ?? '',
        annual_income: profile.annual_income === null ? '' : String(profile.annual_income),
        is_disabled: profile.is_disabled ?? false,
        education: profile.education ?? '',
        marital_status: profile.marital_status ?? '',
        state: profile.state ?? '',
        district: profile.district ?? '',
        locality: profile.locality ?? '',
        pincode: profile.pincode ?? '',
      }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile])

  useEffect(() => {
    let cancelled = false
    void referenceApi
      .locations()
      .then((result) => {
        if (!cancelled) setLocations(result)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  if (!profile) return <LoadingScreen />

  const districts = locations && form.state ? (locations.districts_by_state[form.state] ?? []) : []

  const validateStep = (): string | null => {
    if (step === 0) {
      if (!form.name.trim()) return t('onboarding.errors.nameRequired')
      if (!form.dob) return t('onboarding.errors.dobRequired')
      if (form.annual_income === '' || Number(form.annual_income) < 0)
        return t('onboarding.errors.incomeInvalid')
    }
    if (step === 1) {
      if (!form.state) return t('onboarding.errors.stateRequired')
      if (!form.district) return t('onboarding.errors.districtRequired')
      if (!/^\d{6}$/.test(form.pincode)) return t('onboarding.errors.pincodeInvalid')
    }
    if (step === 2 && !form.consentData) {
      return t('onboarding.consentRequired')
    }
    return null
  }

  const goNext = () => {
    const problem = validateStep()
    setFormError(problem)
    if (!problem) setStep((value) => Math.min(value + 1, TOTAL_STEPS - 1))
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const problem = validateStep()
    setFormError(problem)
    if (problem) return

    const payload: ProfileUpdate = {
      name: form.name.trim(),
      dob: form.dob,
      gender: (form.gender || 'prefer_not_to_say') as Gender,
      occupation: form.occupation.trim() || null,
      annual_income: Number(form.annual_income),
      is_disabled: form.is_disabled,
      education: (form.education || null) as EducationLevel | null,
      marital_status: (form.marital_status || null) as MaritalStatus | null,
      state: form.state,
      district: form.district,
      locality: form.locality.trim() || null,
      pincode: form.pincode,
      language: form.language,
      data_processing_consent: form.consentData,
      whatsapp_opt_in: form.consentWhatsapp,
    }

    setBusy(true)
    setError(null)
    try {
      const updated = await profileApi.updateMe(payload)
      setProfile(updated)
      await i18n.changeLanguage(form.language)
      persistLanguage(form.language)
      void navigate('/dashboard', { replace: true })
    } catch (caught) {
      setError(caught)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box
      component="main"
      sx={{ minHeight: '100dvh', backgroundColor: 'mintcream', px: 2, py: { xs: 2, md: 5 } }}
    >
      <Box
        data-ui="onboarding-form"
        sx={{
          maxWidth: 760,
          mx: 'auto',
          p: { xs: 2, md: 4 },
          backgroundColor: 'white',
          borderLeft: '5px solid darkgreen',
        }}
      >
        <Box component="header" sx={{ mb: 3 }}>
          <Typography variant="h3" component="p" sx={{ color: 'darkgreen' }}>
            {t('common.appName')}
          </Typography>
          <Typography color="text.secondary">{t('common.serviceDescriptor')}</Typography>
        </Box>
        <Stack spacing={2} sx={{ mb: 2 }}>
          <Typography variant="h2" component="h1" sx={{ color: 'darkgreen' }}>
            {t('onboarding.title')}
          </Typography>
          <Typography color="text.secondary">{t('onboarding.subtitle')}</Typography>
          <Stepper activeStep={step} alternativeLabel>
            <Step>
              <StepLabel>{t('onboarding.stepPersonal')}</StepLabel>
            </Step>
            <Step>
              <StepLabel>{t('onboarding.stepLocation')}</StepLabel>
            </Step>
            <Step>
              <StepLabel>{t('onboarding.stepConsent')}</StepLabel>
            </Step>
          </Stepper>
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center' }}>
            {t('onboarding.stepOf', { current: step + 1, total: TOTAL_STEPS })}
          </Typography>
        </Stack>

        <ErrorBanner error={error} />

        <Box component="form" onSubmit={submit} noValidate>
          <Stack spacing={1}>
            {step === 0 ? (
              <>
                <TextField
                  label={t('onboarding.name')}
                  value={form.name}
                  onChange={(event) => update('name', event.target.value)}
                  autoComplete="name"
                  required
                />
                <TextField
                  label={t('onboarding.dob')}
                  type="date"
                  value={form.dob}
                  onChange={(event) => update('dob', event.target.value)}
                  InputLabelProps={{ shrink: true }}
                  inputProps={{ max: new Date().toISOString().slice(0, 10) }}
                  required
                />
                <FormControl fullWidth margin="normal">
                  <InputLabel id="gender-label">{t('onboarding.gender')}</InputLabel>
                  <Select
                    labelId="gender-label"
                    label={t('onboarding.gender')}
                    value={form.gender}
                    onChange={(event) => update('gender', event.target.value as Gender)}
                  >
                    {GENDERS.map((value) => (
                      <MenuItem key={value} value={value}>
                        {t(GENDER_KEYS[value])}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <TextField
                  label={t('onboarding.occupation')}
                  value={form.occupation}
                  onChange={(event) => update('occupation', event.target.value)}
                />
                <TextField
                  label={t('onboarding.annualIncome')}
                  value={form.annual_income}
                  onChange={(event) =>
                    update('annual_income', event.target.value.replace(/\D/g, '').slice(0, 9))
                  }
                  inputProps={{ inputMode: 'numeric' }}
                  required
                />
                <FormControlLabel
                  sx={{ mt: 1 }}
                  control={
                    <Checkbox
                      checked={form.is_disabled}
                      onChange={(event) => update('is_disabled', event.target.checked)}
                    />
                  }
                  label={t('onboarding.isDisabled')}
                />
                <FormControl fullWidth margin="normal">
                  <InputLabel id="education-label">{t('onboarding.education')}</InputLabel>
                  <Select
                    labelId="education-label"
                    label={t('onboarding.education')}
                    value={form.education}
                    onChange={(event) =>
                      update('education', event.target.value as EducationLevel | '')
                    }
                  >
                    <MenuItem value="">
                      <em>{t('common.optional')}</em>
                    </MenuItem>
                    {EDUCATIONS.map((value) => (
                      <MenuItem key={value} value={value}>
                        {t(EDUCATION_KEYS[value])}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <FormControl fullWidth margin="normal">
                  <InputLabel id="marital-label">{t('onboarding.maritalStatus')}</InputLabel>
                  <Select
                    labelId="marital-label"
                    label={t('onboarding.maritalStatus')}
                    value={form.marital_status}
                    onChange={(event) =>
                      update('marital_status', event.target.value as MaritalStatus | '')
                    }
                  >
                    <MenuItem value="">
                      <em>{t('common.optional')}</em>
                    </MenuItem>
                    {MARITAL.map((value) => (
                      <MenuItem key={value} value={value}>
                        {t(MARITAL_KEYS[value])}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </>
            ) : null}

            {step === 1 ? (
              <>
                <FormControl fullWidth margin="normal">
                  <InputLabel id="state-label">{t('onboarding.state')}</InputLabel>
                  <Select
                    labelId="state-label"
                    label={t('onboarding.state')}
                    value={form.state}
                    onChange={(event) => {
                      update('state', event.target.value)
                      update('district', '')
                    }}
                    required
                  >
                    {(locations?.states ?? []).map((value) => (
                      <MenuItem key={value} value={value}>
                        {value}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <FormControl fullWidth margin="normal" disabled={!form.state}>
                  <InputLabel id="district-label">{t('onboarding.district')}</InputLabel>
                  <Select
                    labelId="district-label"
                    label={t('onboarding.district')}
                    value={form.district}
                    onChange={(event) => update('district', event.target.value)}
                    required
                  >
                    {(districts.length ? districts : form.district ? [form.district] : []).map(
                      (value) => (
                        <MenuItem key={value} value={value}>
                          {value}
                        </MenuItem>
                      ),
                    )}
                  </Select>
                </FormControl>
                <TextField
                  label={t('onboarding.locality')}
                  value={form.locality}
                  onChange={(event) => update('locality', event.target.value)}
                />
                <TextField
                  label={t('onboarding.pincode')}
                  value={form.pincode}
                  onChange={(event) =>
                    update('pincode', event.target.value.replace(/\D/g, '').slice(0, 6))
                  }
                  inputProps={{ inputMode: 'numeric' }}
                  required
                />
                <FormControl fullWidth margin="normal">
                  <InputLabel id="onboarding-language-label">{t('onboarding.language')}</InputLabel>
                  <Select
                    labelId="onboarding-language-label"
                    label={t('onboarding.language')}
                    value={form.language}
                    onChange={async (event) => {
                      const code = event.target.value as LanguageCode
                      update('language', code)
                      await i18n.changeLanguage(code)
                      persistLanguage(code)
                    }}
                  >
                    {SUPPORTED_LANGUAGES.map((language) => (
                      <MenuItem key={language.code} value={language.code}>
                        {language.nativeName}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </>
            ) : null}

            {step === 2 ? (
              <>
                <Typography variant="h3" component="h2">
                  {t('onboarding.consentTitle')}
                </Typography>
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={form.consentData}
                      onChange={(event) => update('consentData', event.target.checked)}
                    />
                  }
                  label={t('onboarding.consentData')}
                />
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={form.consentWhatsapp}
                      onChange={(event) => update('consentWhatsapp', event.target.checked)}
                    />
                  }
                  label={t('onboarding.consentWhatsapp')}
                />
                <Alert severity="info">
                  {t('onboarding.policyNote', { version: profile.consent_version ?? '2026-10-01' })}
                </Alert>
              </>
            ) : null}
          </Stack>

          {formError ? (
            <Alert severity="warning" role="alert" sx={{ mt: 2 }}>
              {formError}
            </Alert>
          ) : null}

          <Stack direction="row" spacing={2} sx={{ mt: 3 }}>
            {step > 0 ? (
              <Button variant="outlined" onClick={() => setStep((value) => value - 1)} disabled={busy}>
                {t('common.back')}
              </Button>
            ) : null}
            {step < TOTAL_STEPS - 1 ? (
              <Button variant="contained" onClick={goNext} sx={{ flexGrow: 1 }} size="large">
                {t('common.continue')}
              </Button>
            ) : (
              <Button
                type="submit"
                variant="contained"
                sx={{ flexGrow: 1 }}
                size="large"
                disabled={busy}
              >
                {busy ? t('onboarding.saving') : t('onboarding.finish')}
              </Button>
            )}
          </Stack>
        </Box>
      </Box>
    </Box>
  )
}
