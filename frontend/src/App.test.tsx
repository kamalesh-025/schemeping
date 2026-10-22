import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider } from '@mui/material/styles'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { App } from './App'
import { AuthProvider } from './auth/AuthContext'
import { loadMsg91Widget, sendWidgetOtp } from './auth/msg91Widget'
import { theme } from './theme/theme'
import type { AuthConfig, FamilyMember, Profile } from './api/types'

// jsdom cannot load MSG91's third-party SDK, so the widget is stubbed for the
// whole file. Tests that exercise the widget flow assert on these calls.
vi.mock('./auth/msg91Widget', () => ({
  WIDGET_CAPTCHA_ELEMENT_ID: 'msg91-widget-captcha',
  loadMsg91Widget: vi.fn(async () => undefined),
  sendWidgetOtp: vi.fn(async () => undefined),
  verifyWidgetOtp: vi.fn(async () => 'widget-access-token'),
}))

const COMPLETE_PROFILE: Profile = {
  id: 1,
  mobile: '9876543210',
  name: 'Lakshmi',
  dob: '1985-04-12',
  gender: 'female',
  occupation: 'farmer',
  annual_income: 180000,
  is_disabled: false,
  education: 'secondary',
  marital_status: 'married',
  state: 'Tamil Nadu',
  district: 'Chennai',
  locality: 'Egmore',
  pincode: '600008',
  language: 'en',
  consent_data_processing: true,
  consent_whatsapp: true,
  consent_version: '2026-10-01',
  consented_at: '2026-10-19T06:00:00Z',
  whatsapp_opted_out_at: null,
  profile_complete: true,
  age: 41,
  is_senior: false,
  created_at: '2026-10-19T06:00:00Z',
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

const references = {
  states: ['Tamil Nadu'],
  districts_by_state: { 'Tamil Nadu': ['Chennai', 'Madurai'] },
}

interface Harness {
  authenticated: boolean
  profile: Profile
  requests: string[]
  familyMembers?: FamilyMember[]
  authConfig?: AuthConfig
  loginFails?: boolean
  whatsappDelivery?: boolean
}

function installFetch(harness: Harness) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const path = url.replace('http://localhost', '')
    const method = (init?.method ?? 'GET').toUpperCase()
    harness.requests.push(`${method} ${path}`)

    if (path === '/api/v1/me' && method === 'GET') {
      return harness.authenticated
        ? json(harness.profile)
        : json({ detail: 'Not authenticated' }, 401)
    }
    if (path === '/api/v1/auth/config') {
      return json(
        harness.authConfig ?? {
          mode: 'password',
          password_min_length: 8,
          widget_id: null,
          widget_token: null,
        },
      )
    }
    if (path === '/api/v1/auth/login' || path === '/api/v1/auth/register') {
      if (harness.loginFails) {
        return json({ detail: 'Mobile number or password is incorrect.' }, 401)
      }
      harness.authenticated = true
      return json(
        { id: 1, name: null, mobile: '9876543210', language: 'en' },
        method === 'POST' && path.endsWith('/register') ? 201 : 200,
      )
    }
    if (path === '/api/v1/auth/otp/request') {
      return json({ message: 'sent', expires_in_seconds: 300, resend_after_seconds: 30 })
    }
    if (path === '/api/v1/auth/otp/verify') {
      harness.authenticated = true
      return json({ id: 1, name: null, mobile: '9876543210', language: 'en' })
    }
    if (path === '/api/v1/auth/logout') {
      harness.authenticated = false
      return new Response(null, { status: 204 })
    }
    if (path === '/api/v1/auth/password') {
      return new Response(null, { status: 204 })
    }
    if (path === '/api/v1/family') return json(harness.familyMembers ?? [])
    if (path === '/api/v1/reference/locations') return json(references)
    if (path === '/api/v1/features') {
      return json({
        whatsapp_delivery: harness.whatsappDelivery ?? false,
        whatsapp_click_to_chat: true,
      })
    }
    if (path.startsWith('/api/v1/schemes/1/send-whatsapp') && method === 'POST') {
      return json({ status: 'queued', reason: null, notification_id: 7 })
    }
    if (path === '/api/v1/me/consents') {
      return json({
        data_processing: true,
        whatsapp: true,
        policy_version: '2026-10-01',
        consented_at: '2026-10-19T06:00:00Z',
        whatsapp_opted_out_at: null,
        notification_preferences: {
          new_schemes: true,
          family_milestones: true,
          deadlines: true,
          festival: true,
        },
      })
    }
    if (path.startsWith('/api/v1/schemes/1')) {
      return json({
        id: 1,
        slug: 'test-scheme',
        name: 'Test scheme',
        department: 'Test department',
        level: 'state',
        state: 'Tamil Nadu',
        category: 'education',
        scope: 'individual',
        benefit_summary: 'Cash support every year.',
        benefit_amount: '₹1,000',
        benefit_type: 'cash',
        deadline: null,
        days_remaining: null,
        apply_url: null,
        source_url: 'https://example.gov.in/test-scheme',
        last_verified_on: '2026-10-15',
        required_documents: [{ name: 'Ration card', notes: null }],
        application_steps: [{ title: 'Visit the e-Sevai centre', detail: null }],
        eligibility_status: 'eligible',
        why_qualify: ['You qualify: State is Tamil Nadu.'],
        missing_fields: [],
        person: path.includes('person=1') ? 1 : 'me',
        language: 'en',
        translation: {
          simple_title: 'Test scheme in simple words',
          simple_description: 'Cash support explained simply.',
          simple_benefits: ['₹1,000 every year'],
          simple_steps: ['Visit the e-Sevai centre'],
          cached: true,
          fallback: false,
        },
      })
    }
    if (path === '/api/v1/facilities/nearest') {
      return json({
        total: 1,
        facilities: [
          {
            id: 1,
            name: 'Egmore e-Sevai',
            type: 'e_sevai',
            address: 'Main road, Egmore',
            district: 'Chennai',
            state: 'Tamil Nadu',
            pincode: '600008',
            phone: '1234567890',
            working_hours: '9am to 5pm',
            lat: 13.08,
            lon: 80.26,
            distance_km: 1.4,
          },
        ],
      })
    }
    if (path === '/api/v1/facilities') {
      return json({ total: 0, facilities: [] })
    }
    if (path === '/api/v1/eligibility/summary') {
      return json({
        people: [
          {
            kind: 'me',
            id: null,
            name: null,
            counts: { eligible: 1, needs_info: 0, not_eligible: 1, total: 2 },
            by_category: {},
          },
        ],
      })
    }
    if (path.startsWith('/api/v1/eligibility') && method === 'GET') {
      return json({
        total: 2,
        cards: [
          {
            scheme_id: 1,
            slug: 'test-scheme',
            name: 'Test scheme',
            scope: 'individual',
            category: 'education',
            level: 'state',
            state: 'Tamil Nadu',
            department: 'Test department',
            benefit_summary: 'Cash support every year.',
            benefit_amount: '₹1,000',
            benefit_type: 'cash',
            priority: 'normal',
            status: 'eligible',
            reason_line: 'You qualify: State is Tamil Nadu.',
            missing_fields: [],
            deadline: null,
            days_remaining: null,
            last_verified_on: '2026-10-15',
          },
          {
            scheme_id: 2,
            slug: 'test-scheme-two',
            name: 'Second scheme',
            scope: 'family',
            category: 'housing',
            level: 'state',
            state: 'Tamil Nadu',
            department: 'Test department',
            benefit_summary: 'Housing support.',
            benefit_amount: null,
            benefit_type: 'service',
            priority: 'medium',
            status: 'not_eligible',
            reason_line: 'Household income must be less than ₹10',
            missing_fields: [],
            deadline: null,
            days_remaining: null,
            last_verified_on: '2026-10-15',
          },
        ],
      })
    }
    return json({ detail: 'Not found' }, 404)
  })
}

function renderApp(harness: Harness, entries: string[] = ['/']) {
  const fetchMock = installFetch(harness)
  vi.stubGlobal('fetch', fetchMock)
  return render(
    <ThemeProvider theme={theme}>
      <MemoryRouter initialEntries={entries}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </ThemeProvider>,
  )
}

function harness(overrides: Partial<Harness> = {}): Harness {
  return {
    authenticated: false,
    profile: COMPLETE_PROFILE,
    requests: [],
    ...overrides,
  }
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('App', () => {
  it('shows the password sign-in screen for a signed-out visitor', async () => {
    renderApp(harness(), ['/'])
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Language' })).toBeVisible()
    expect(screen.getByRole('tab', { name: 'Create account' })).toBeInTheDocument()
    expect(screen.getByLabelText(/^Password/)).toBeInTheDocument()
  })

  it('signs in with a mobile number and password', async () => {
    const state = harness()
    renderApp(state, ['/'])
    const user = userEvent.setup()

    await user.type(await screen.findByLabelText(/Mobile number/), '9876543210')
    await user.type(screen.getByLabelText(/^Password/), 'schemeping-test-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(
      await screen.findByRole('heading', { name: 'Your scheme matches' }),
    ).toBeInTheDocument()
    expect(state.requests).toContain('POST /api/v1/auth/login')
  })

  it('creates an account from the sign-up tab', async () => {
    const state = harness()
    renderApp(state, ['/'])
    const user = userEvent.setup()

    await user.click(await screen.findByRole('tab', { name: 'Create account' }))
    await user.type(screen.getByLabelText(/Mobile number/), '9876543210')
    await user.type(screen.getByLabelText(/^Password/), 'schemeping-test-password')
    await user.type(screen.getByLabelText(/^Confirm password/), 'schemeping-test-password')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(
      await screen.findByRole('heading', { name: 'Your scheme matches' }),
    ).toBeInTheDocument()
    expect(state.requests).toContain('POST /api/v1/auth/register')
  })

  it('does not say whether the number or the password was wrong', async () => {
    const state = harness({ loginFails: true })
    renderApp(state, ['/'])
    const user = userEvent.setup()

    await user.type(await screen.findByLabelText(/Mobile number/), '9876543210')
    await user.type(screen.getByLabelText(/^Password/), 'not-the-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(
      await screen.findByText('The mobile number or password is incorrect.'),
    ).toBeInTheDocument()
  })

  it('requests an OTP and reveals the code field', async () => {
    const state = harness({
      authConfig: {
        mode: 'server',
        password_min_length: 8,
        widget_id: null,
        widget_token: null,
      },
    })
    renderApp(state, ['/'])
    const user = userEvent.setup()

    const mobile = await screen.findByLabelText(/Mobile number/)
    await user.type(mobile, '9876543210')
    await user.click(screen.getByRole('button', { name: 'Send OTP' }))

    expect(await screen.findByLabelText(/One-time password/)).toBeInTheDocument()
    expect(
      screen.getByText(/No SMS is sent.*\[DEV OTP\]/),
    ).toBeInTheDocument()
    expect(state.requests).toContain('POST /api/v1/auth/otp/request')
    expect(screen.getByRole('button', { name: 'Change mobile number' })).toBeInTheDocument()
  })

  it('uses the MSG91 widget when the backend reports widget mode', async () => {
    vi.mocked(loadMsg91Widget).mockResolvedValue(undefined)
    const state = harness({
      authConfig: {
        mode: 'widget',
        password_min_length: 8,
        widget_id: 'widget-id',
        widget_token: 'widget-token',
      },
    })
    renderApp(state, ['/'])

    // The widget hint replaces the development-only instructions.
    expect(await screen.findByText(/We will send a one-time code/)).toBeInTheDocument()
    expect(screen.queryByText(/\[DEV OTP\]/)).not.toBeInTheDocument()
    expect(loadMsg91Widget).toHaveBeenCalledWith('widget-id', 'widget-token')

    const user = userEvent.setup()
    const button = screen.getByRole('button', { name: 'Send OTP' })
    await user.type(screen.getByLabelText(/Mobile number/), '9876543210')

    // The button unlocks only once the third-party SDK is initialised.
    await waitFor(() => expect(button).toBeEnabled())
    await user.click(button)

    expect(await screen.findByLabelText(/One-time password/)).toBeInTheDocument()
    expect(sendWidgetOtp).toHaveBeenCalledWith('9876543210')
    // MSG91 sends the code, so the backend OTP route must never be called.
    expect(state.requests).not.toContain('POST /api/v1/auth/otp/request')
  })

  it('reports a misconfigured widget instead of falling back to the server flow', async () => {
    const state = harness({
      authConfig: {
        mode: 'widget',
        password_min_length: 8,
        widget_id: null,
        widget_token: null,
      },
    })
    renderApp(state, ['/'])

    expect(await screen.findByText(/Sign-in is not ready on this device/)).toBeInTheDocument()
    expect(screen.queryByText(/\[DEV OTP\]/)).not.toBeInTheDocument()
  })

  it('routes a signed-in user with an incomplete profile to onboarding', async () => {
    const state = harness({
      authenticated: true,
      profile: { ...COMPLETE_PROFILE, name: null, dob: null, state: null, profile_complete: false },
    })
    renderApp(state, ['/'])

    expect(
      await screen.findByRole('heading', { name: 'Tell us about you' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Step 1 of 3/)).toBeInTheDocument()
  })

  it('shows the dashboard with eligible schemes for a complete profile', async () => {
    const state = harness({ authenticated: true })
    renderApp(state, ['/'])

    expect(await screen.findByRole('heading', { name: 'Your scheme matches' })).toBeInTheDocument()
    expect(await screen.findByText('Test scheme')).toBeInTheDocument()
    expect(screen.getByText('You qualify: State is Tamil Nadu.')).toBeInTheDocument()
    expect(state.requests).toContain('GET /api/v1/eligibility/summary')
    const cardsRequest = state.requests.find((path) =>
      path.startsWith('GET /api/v1/eligibility?'),
    )
    expect(cardsRequest).toBeDefined()
    expect(cardsRequest).not.toContain('scope=all')
    expect(cardsRequest).not.toContain('category=all')
  })

  it('filters matches by category when a chip is tapped', async () => {
    const state = harness({ authenticated: true })
    renderApp(state, ['/dashboard'])
    const user = userEvent.setup()

    await screen.findByText('Test scheme')
    await user.click(screen.getByRole('button', { name: 'Education' }))

    await waitFor(() => {
      expect(state.requests.some((path) => path.includes('category=education'))).toBe(true)
    })
  })

  it('logs out from the home page and returns to the sign-in screen', async () => {
    const state = harness({ authenticated: true })
    renderApp(state, ['/dashboard'])
    const user = userEvent.setup()

    await screen.findByText('Test scheme')

    const logoutButtons = await screen.findAllByRole('button', { name: 'Log out' })
    await user.click(logoutButtons[0])

    const dialog = await screen.findByRole('dialog')
    expect(
      within(dialog).getByRole('heading', { name: 'Log out of SchemePing?' }),
    ).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Log out' }))

    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
    expect(state.requests).toContain('POST /api/v1/auth/logout')
  })

  it('shows the family screen with an empty state for a complete profile', async () => {
    const state = harness({ authenticated: true })
    renderApp(state, ['/family'])

    expect(await screen.findByRole('heading', { name: 'My family' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Household register' })).toBeInTheDocument()
    expect(await screen.findByText('You have not added anyone yet.')).toBeInTheDocument()
    expect(state.requests).toContain('GET /api/v1/family')
  })

  it('shows family member details and the matching guidance', async () => {
    const state = harness({
      authenticated: true,
      familyMembers: [
        {
          id: 11,
          name: 'Demo Student',
          relationship: 'daughter',
          dob: '2010-04-12',
          gender: 'female',
          occupation: null,
          education_status: 'secondary',
          annual_income: null,
          is_disabled: false,
          is_student: true,
          is_widow: false,
          age: 16,
          is_senior: false,
          is_minor: true,
          created_at: '2026-10-19T06:00:00Z',
          updated_at: '2026-10-19T06:00:00Z',
        },
      ],
    })
    renderApp(state, ['/family'])

    expect(await screen.findByRole('heading', { name: 'Demo Student' })).toBeInTheDocument()
    expect(screen.getByText('16 years')).toBeInTheDocument()
    expect(screen.getByText('Student')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'How family matching works' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View scheme matches' })).toHaveAttribute(
      'href',
      '/dashboard',
    )
  })

  it('shows language, WhatsApp consent and notification categories in Settings', async () => {
    const state = harness({ authenticated: true })
    renderApp(state, ['/settings'])

    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Language' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'WhatsApp messages' })).toBeInTheDocument()
    expect(screen.getByText('Mobile ending in 3210')).toBeInTheDocument()
    expect(screen.queryByText('9876543210')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Your privacy controls' })).toBeInTheDocument()
    expect(
      await screen.findByRole('checkbox', { name: 'New schemes you qualify for' }),
    ).toBeChecked()
  })

  it('changes the password from Settings', async () => {
    const state = harness({ authenticated: true })
    renderApp(state, ['/settings'])
    const user = userEvent.setup()

    expect(await screen.findByRole('heading', { name: 'Password' })).toBeInTheDocument()
    await user.type(screen.getByLabelText(/^Current password/), 'old-password')
    await user.type(screen.getByLabelText(/^New password/), 'a-brand-new-password')
    await user.type(screen.getByLabelText(/^Confirm new password/), 'a-brand-new-password')
    await user.click(screen.getByRole('button', { name: 'Change password' }))

    expect(await screen.findByText('Your password has been changed.')).toBeInTheDocument()
    expect(state.requests).toContain('POST /api/v1/auth/password')
  })

  it('exposes a family form from the empty state', async () => {
    const state = harness({ authenticated: true })
    renderApp(state, ['/family'])
    const user = userEvent.setup()

    const addButtons = await screen.findAllByRole('button', { name: 'Add family member' })
    await user.click(addButtons[addButtons.length - 1])

    expect(await screen.findByRole('heading', { name: 'Add family member' })).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByLabelText(/Full name/)).toBeInTheDocument()
    })
  })

  it('offers the free WhatsApp link when server delivery is not configured', async () => {
    const state = harness({ authenticated: true })
    renderApp(state, ['/schemes/1?person=me'])

    await screen.findByText('Test scheme in simple words')
    const link = await screen.findByRole('link', { name: 'Send on WhatsApp' })

    expect(link).toHaveAttribute(
      'href',
      expect.stringContaining('https://wa.me/?text='),
    )
    expect(
      state.requests.some((path) =>
        path.startsWith('POST /api/v1/schemes/1/send-whatsapp'),
      ),
    ).toBe(false)
  })

  it('shows the scheme detail in simple language from the dashboard', async () => {
    const state = harness({ authenticated: true })
    renderApp(state, ['/schemes/1?person=me'])

    expect(await screen.findByText('Test scheme in simple words')).toBeInTheDocument()
    expect(await screen.findByText('You qualify: State is Tamil Nadu.')).toBeInTheDocument()
    expect(screen.getByLabelText('Ration card')).toBeInTheDocument()
    expect(screen.getByText('Last verified on 2026-10-15.')).toBeInTheDocument()
    expect(state.requests.some((path) => path.startsWith('GET /api/v1/schemes/1'))).toBe(true)
  })

  it('queues an opted-in WhatsApp summary and provides the free share link', async () => {
    const state = harness({ authenticated: true, whatsappDelivery: true })
    renderApp(state, ['/schemes/1?person=me'])
    const user = userEvent.setup()

    await screen.findByText('Test scheme in simple words')
    await user.click(screen.getByRole('button', { name: 'Send to WhatsApp' }))

    expect(await screen.findByText(/message is queued/i)).toBeInTheDocument()
    expect(
      state.requests.some((path) =>
        path.startsWith('POST /api/v1/schemes/1/send-whatsapp?'),
      ),
    ).toBe(true)
    expect(screen.getByRole('link', { name: 'Share using WhatsApp' })).toHaveAttribute(
      'href',
      expect.stringContaining('https://wa.me/?text='),
    )
  })

  it('re-requests the scheme in the chosen language', async () => {
    const state = harness({ authenticated: true })
    renderApp(state, ['/schemes/1'])
    const user = userEvent.setup()

    await screen.findByText('Test scheme in simple words')
    await user.click(screen.getByRole('button', { name: 'தமிழ்' }))

    await waitFor(() => {
      expect(state.requests.some((path) => path.includes('lang=ta'))).toBe(true)
    })
  })

  it('shows the apply page steps and asks before using geolocation for facilities', async () => {
    const state = harness({ authenticated: true })
    renderApp(state, ['/schemes/1/apply'])

    expect(await screen.findByText('1. Visit the e-Sevai centre')).toBeInTheDocument()
    expect(screen.getByText(/We can find government centres near you/)).toBeInTheDocument()
    expect(screen.queryByText('Egmore e-Sevai')).not.toBeInTheDocument()
    expect(state.requests.some((path) => path === 'GET /api/v1/facilities')).toBe(false)
  })
})
