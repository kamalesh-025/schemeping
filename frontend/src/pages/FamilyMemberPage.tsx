import { useEffect, useState, type FormEvent } from 'react'
import {
  Box,
  Button,
  Checkbox,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Snackbar,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { ErrorBanner } from '../components/ErrorBanner'
import { LoadingScreen } from '../components/LoadingScreen'
import { familyApi } from '../api/endpoints'
import type {
  EducationLevel,
  FamilyMemberInput,
  Gender,
  Relationship,
} from '../api/types'

const RELATIONSHIPS: Relationship[] = [
  'spouse',
  'son',
  'daughter',
  'father',
  'mother',
  'brother',
  'sister',
  'grandfather',
  'grandmother',
  'other',
]
const RELATIONSHIP_KEYS: Record<Relationship, string> = {
  spouse: 'family.relationshipSpouse',
  son: 'family.relationshipSon',
  daughter: 'family.relationshipDaughter',
  father: 'family.relationshipFather',
  mother: 'family.relationshipMother',
  brother: 'family.relationshipBrother',
  sister: 'family.relationshipSister',
  grandfather: 'family.relationshipGrandfather',
  grandmother: 'family.relationshipGrandmother',
  other: 'family.relationshipOther',
}
const GENDERS: Gender[] = ['female', 'male', 'other', 'prefer_not_to_say']
const GENDER_KEYS: Record<Gender, string> = {
  female: 'onboarding.genderFemale',
  male: 'onboarding.genderMale',
  other: 'onboarding.genderOther',
  prefer_not_to_say: 'onboarding.genderPreferNotToSay',
}
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

interface FormState {
  name: string
  relationship: Relationship | ''
  dob: string
  gender: Gender | ''
  occupation: string
  education_status: EducationLevel | ''
  annual_income: string
  is_disabled: boolean
  is_student: boolean
  is_widow: boolean
}

const EMPTY: FormState = {
  name: '',
  relationship: '',
  dob: '',
  gender: '',
  occupation: '',
  education_status: '',
  annual_income: '',
  is_disabled: false,
  is_student: false,
  is_widow: false,
}

export function FamilyMemberPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { id } = useParams<{ id: string }>()
  const isEdit = Boolean(id)

  const [form, setForm] = useState<FormState>(EMPTY)
  const [loading, setLoading] = useState(isEdit)
  const [error, setError] = useState<unknown>(null)
  const [nameError, setNameError] = useState(false)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((current) => ({ ...current, [key]: value }))

  useEffect(() => {
    if (!id) return
    let cancelled = false
    void familyApi
      .get(Number(id))
      .then((member) => {
        if (cancelled) return
        setForm({
          name: member.name,
          relationship: member.relationship,
          dob: member.dob ?? '',
          gender: member.gender ?? '',
          occupation: member.occupation ?? '',
          education_status: member.education_status ?? '',
          annual_income: member.annual_income === null ? '' : String(member.annual_income),
          is_disabled: member.is_disabled ?? false,
          is_student: member.is_student,
          is_widow: member.is_widow,
        })
      })
      .catch((caught) => {
        if (!cancelled) setError(caught)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [id])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    if (!form.name.trim()) {
      setNameError(true)
      return
    }
    setNameError(false)

    const payload: FamilyMemberInput = {
      name: form.name.trim(),
      relationship: (form.relationship || 'other') as Relationship,
      dob: form.dob || null,
      gender: (form.gender || null) as Gender | null,
      occupation: form.occupation.trim() || null,
      education_status: (form.education_status || null) as EducationLevel | null,
      annual_income: form.annual_income === '' ? null : Number(form.annual_income),
      is_disabled: form.is_disabled,
      is_student: form.is_student,
      is_widow: form.is_widow,
    }

    setBusy(true)
    try {
      if (isEdit) {
        await familyApi.update(Number(id), payload)
      } else {
        await familyApi.create(payload)
      }
      setSaved(true)
      window.setTimeout(() => void navigate('/family', { replace: true }), 500)
    } catch (caught) {
      setError(caught)
      setBusy(false)
    }
  }

  if (loading) return <LoadingScreen />

  return (
    <Box
      component="form"
      onSubmit={submit}
      noValidate
      data-ui="family-member-form"
      sx={{ p: { xs: 2, sm: 3 }, backgroundColor: 'white', borderLeft: '5px solid darkgreen' }}
    >
      <Stack spacing={1}>
        <Box className="page-heading">
          <Typography variant="h2" component="h1" sx={{ color: 'darkgreen' }}>
            {isEdit ? t('family.editTitle') : t('family.addTitle')}
          </Typography>
        </Box>

        <ErrorBanner error={error} />

        <TextField
          label={t('family.name')}
          value={form.name}
          onChange={(event) => update('name', event.target.value)}
          error={nameError}
          helperText={nameError ? t('onboarding.errors.nameRequired') : ' '}
          required
        />

        <FormControl fullWidth margin="normal">
          <InputLabel id="relationship-label">{t('family.relationship')}</InputLabel>
          <Select
            labelId="relationship-label"
            label={t('family.relationship')}
            value={form.relationship}
            onChange={(event) => update('relationship', event.target.value as Relationship)}
            required
          >
            {RELATIONSHIPS.map((value) => (
              <MenuItem key={value} value={value}>
                {t(RELATIONSHIP_KEYS[value])}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <TextField
          label={t('family.dob')}
          type="date"
          value={form.dob}
          onChange={(event) => update('dob', event.target.value)}
          InputLabelProps={{ shrink: true }}
          inputProps={{ max: new Date().toISOString().slice(0, 10) }}
        />

        <FormControl fullWidth margin="normal">
          <InputLabel id="member-gender-label">{t('family.gender')}</InputLabel>
          <Select
            labelId="member-gender-label"
            label={t('family.gender')}
            value={form.gender}
            onChange={(event) => update('gender', event.target.value as Gender | '')}
          >
            <MenuItem value="">
              <em>{t('common.optional')}</em>
            </MenuItem>
            {GENDERS.map((value) => (
              <MenuItem key={value} value={value}>
                {t(GENDER_KEYS[value])}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <TextField
          label={t('family.occupation')}
          value={form.occupation}
          onChange={(event) => update('occupation', event.target.value)}
        />

        <FormControl fullWidth margin="normal">
          <InputLabel id="education-status-label">{t('family.educationStatus')}</InputLabel>
          <Select
            labelId="education-status-label"
            label={t('family.educationStatus')}
            value={form.education_status}
            onChange={(event) =>
              update('education_status', event.target.value as EducationLevel | '')
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

        <TextField
          label={t('family.annualIncome')}
          value={form.annual_income}
          onChange={(event) =>
            update('annual_income', event.target.value.replace(/\D/g, '').slice(0, 9))
          }
          inputProps={{ inputMode: 'numeric' }}
        />

        <FormControlLabel
          control={
            <Checkbox
              checked={form.is_student}
              onChange={(event) => update('is_student', event.target.checked)}
            />
          }
          label={t('family.isStudent')}
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={form.is_disabled}
              onChange={(event) => update('is_disabled', event.target.checked)}
            />
          }
          label={t('family.isDisabled')}
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={form.is_widow}
              onChange={(event) => update('is_widow', event.target.checked)}
            />
          }
          label={t('family.isWidow')}
        />

        <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
          <Button variant="outlined" onClick={() => void navigate('/family')} disabled={busy}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" variant="contained" size="large" sx={{ flexGrow: 1 }} disabled={busy}>
            {t('common.save')}
          </Button>
        </Stack>
      </Stack>

      <Snackbar
        open={saved}
        autoHideDuration={1500}
        message={t('family.savedMessage')}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      />
    </Box>
  )
}
