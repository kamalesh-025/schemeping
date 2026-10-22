import { useCallback, useEffect, useState } from 'react'
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Link as MuiLink,
  Stack,
  Typography,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import EditOutlinedIcon from '@mui/icons-material/EditOutlined'
import { Link as RouterLink, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { ConfirmDialog } from '../components/ConfirmDialog'
import { EmptyState } from '../components/EmptyState'
import { ErrorBanner } from '../components/ErrorBanner'
import { LoadingScreen } from '../components/LoadingScreen'
import { familyApi } from '../api/endpoints'
import type { FamilyMember, Relationship } from '../api/types'

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

export function FamilyPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const [members, setMembers] = useState<FamilyMember[] | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [pendingDelete, setPendingDelete] = useState<FamilyMember | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      setMembers(await familyApi.list())
    } catch (caught) {
      setError(caught)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const remove = async (member: FamilyMember) => {
    try {
      await familyApi.remove(member.id)
      await load()
    } catch (caught) {
      setError(caught)
    }
  }

  const membersWithSupport = members?.filter(
    (member) =>
      member.is_senior ||
      member.is_minor ||
      member.is_student ||
      member.is_disabled ||
      member.is_widow,
  ).length

  return (
    <Stack spacing={3}>
      <Box className="family-page-header">
        <Box className="page-heading">
          <Typography variant="h2" component="h1" sx={{ color: 'navy' }}>
            {t('family.title')}
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5 }}>
            {t('family.subtitle')}
          </Typography>
        </Box>
        <Box className="household-actions">
          <Button
            variant="contained"
            size="large"
            startIcon={<AddIcon />}
            onClick={() => void navigate('/family/new')}
          >
            {t('family.addMember')}
          </Button>
        </Box>
      </Box>

      <Box className="household-overview">
        <Box className="household-overview__intro">
          <Typography component="h2" variant="h3">
            {t('family.householdRegister')}
          </Typography>
          <Typography component="p">{t('family.registerIntro')}</Typography>
        </Box>
        <Box className="household-overview__stat">
          <Typography component="span" className="household-overview__value">
            {members?.length ?? '—'}
          </Typography>
          <Typography component="span" className="household-overview__label">
            {t('family.peopleCount', { count: members?.length ?? 0 })}
          </Typography>
        </Box>
        <Box className="household-overview__stat household-overview__stat--support">
          <Typography component="span" className="household-overview__value">
            {membersWithSupport ?? '—'}
          </Typography>
          <Typography component="span" className="household-overview__label">
            {t('family.supportCount')}
          </Typography>
        </Box>
      </Box>

      <ErrorBanner error={error} onRetry={() => void load()} />

      {members === null && !error ? <LoadingScreen /> : null}

      {members && members.length === 0 ? (
        <Box className="family-workspace">
          <Box className="family-empty">
            <EmptyState
              title={t('family.empty')}
              hint={t('family.emptyHint')}
              action={{
                label: t('family.addMember'),
                onClick: () => void navigate('/family/new'),
              }}
            />
          </Box>
          <FamilyGuidance />
        </Box>
      ) : null}

      {members && members.length > 0 ? (
        <Box className="family-workspace">
          <Box className="family-register">
            <Box className="family-register__heading">
              <Typography component="h2" variant="h3">
                {t('family.householdRegister')}
              </Typography>
              <Typography component="p">{t('family.subtitle')}</Typography>
            </Box>
            <Box className="family-register-list">
              {members.map((member) => (
                <Card
                  key={member.id}
                  className={
                    member.is_disabled ||
                    member.is_senior ||
                    member.is_student ||
                    member.is_widow ||
                    member.is_minor
                      ? 'family-register-row family-register-row--support'
                      : 'family-register-row'
                  }
                  data-ui="family-member"
                >
                  <Box className="family-register-row__content">
                    <Box className="family-register-row__identity">
                      <Box className="family-register-row__initial" aria-hidden="true">
                        {member.name.trim().slice(0, 1).toLocaleUpperCase()}
                      </Box>
                      <Box sx={{ minWidth: 0 }}>
                        <MuiLink
                          component={RouterLink}
                          to={`/family/${member.id}/edit`}
                          underline="hover"
                          color="primary"
                        >
                          <Typography variant="h3" component="h3">
                            {member.name}
                          </Typography>
                        </MuiLink>
                        <Typography color="text.secondary">
                          {t(RELATIONSHIP_KEYS[member.relationship])}
                        </Typography>
                      </Box>
                    </Box>

                    <Box className="family-register-row__facts">
                      <Typography component="span" className="family-register-row__fact-label">
                        {t('family.ageLabel')}
                      </Typography>
                      <Typography component="span" className="family-register-row__fact-value">
                        {member.age === null
                          ? t('family.ageUnknown')
                          : t('family.age', { age: member.age })}
                      </Typography>
                      {member.occupation ? (
                        <>
                          <Typography
                            component="span"
                            className="family-register-row__fact-label"
                          >
                            {t('family.occupationLabel')}
                          </Typography>
                          <Typography
                            component="span"
                            className="family-register-row__fact-value"
                          >
                            {member.occupation}
                          </Typography>
                        </>
                      ) : null}
                    </Box>

                    <Stack
                      direction="row"
                      spacing={1}
                      useFlexGap
                      flexWrap="wrap"
                      className="family-register-row__actions"
                    >
                      <Button
                        variant="outlined"
                        startIcon={<EditOutlinedIcon />}
                        onClick={() => void navigate(`/family/${member.id}/edit`)}
                      >
                        {t('common.edit')}
                      </Button>
                      <Button
                        variant="outlined"
                        color="error"
                        startIcon={<DeleteOutlineIcon />}
                        onClick={() => setPendingDelete(member)}
                      >
                        {t('common.delete')}
                      </Button>
                    </Stack>
                  </Box>

                  {(member.is_senior ||
                    member.is_minor ||
                    member.is_student ||
                    member.is_disabled ||
                    member.is_widow) && (
                    <Stack
                      direction="row"
                      spacing={1}
                      useFlexGap
                      flexWrap="wrap"
                      className="family-register-row__details"
                    >
                      {member.is_senior ? <Chip label={t('family.senior')} color="primary" /> : null}
                      {member.is_minor ? <Chip label={t('family.minor')} /> : null}
                      {member.is_student ? <Chip label={t('family.student')} /> : null}
                      {member.is_disabled ? (
                        <Chip label={t('family.disabled')} color="warning" />
                      ) : null}
                      {member.is_widow ? <Chip label={t('family.widow')} /> : null}
                    </Stack>
                  )}
                </Card>
              ))}
            </Box>
          </Box>
          <FamilyGuidance />
        </Box>
      ) : null}

      <ConfirmDialog
        open={pendingDelete !== null}
        title={t('family.removeConfirmTitle')}
        body={t('family.removeConfirmBody', { name: pendingDelete?.name ?? '' })}
        confirmLabel={t('common.delete')}
        destructive
        onConfirm={async () => {
          if (pendingDelete) await remove(pendingDelete)
        }}
        onClose={() => setPendingDelete(null)}
      />
    </Stack>
  )
}

function FamilyGuidance() {
  const { t } = useTranslation()

  return (
    <Card component="aside" className="family-guidance">
      <CardContent>
        <Typography component="h2" variant="h3">
          {t('family.matchingTitle')}
        </Typography>
        <Box component="ol" className="family-guidance__steps">
          <Box component="li">{t('family.matchingStepOne')}</Box>
          <Box component="li">{t('family.matchingStepTwo')}</Box>
          <Box component="li">{t('family.matchingStepThree')}</Box>
        </Box>
        <Box className="family-guidance__note">{t('family.rulesNote')}</Box>
        <Button
          component={RouterLink}
          to="/dashboard"
          variant="outlined"
          size="large"
          sx={{ mt: 2, width: '100%' }}
        >
          {t('family.viewMatches')}
        </Button>
      </CardContent>
    </Card>
  )
}
