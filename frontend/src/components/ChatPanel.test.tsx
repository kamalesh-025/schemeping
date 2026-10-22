import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider } from '@mui/material/styles'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ChatPanel } from './ChatPanel'
import { theme } from '../theme/theme'
import '../i18n'

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('ChatPanel', () => {
  let requests: string[]

  beforeEach(() => {
    requests = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        const path = url.replace('http://localhost', '')
        const method = (init?.method ?? 'GET').toUpperCase()
        requests.push(`${method} ${path}`)

        if (path === '/api/v1/chat/history') {
          return json({
            total: 0,
            messages: [],
          })
        }
        if (path === '/api/v1/chat' && method === 'POST') {
          return json({
            answer: 'You are eligible for the tuition scheme.',
            sources: [{ id: 1, name: 'Tuition Assistance' }],
            language: 'en',
            grounded: true,
          })
        }
        return json({ detail: 'Not found' }, 404)
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function renderPanel() {
    return render(
      <ThemeProvider theme={theme}>
        <ChatPanel />
      </ThemeProvider>,
    )
  }

  it('shows a floating button that opens the chat', async () => {
    const user = userEvent.setup()
    renderPanel()

    const open = screen.getByRole('button', { name: /ask the assistant/i })
    expect(open).toBeTruthy()

    await user.click(open)
    expect(await screen.findByRole('dialog')).toBeTruthy()
    expect(screen.getByPlaceholderText(/type your question/i)).toBeTruthy()
  })

  it('greets the user when the conversation is new', async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.click(screen.getByRole('button', { name: /ask the assistant/i }))

    expect(
      await screen.findByText(/ask me anything about government schemes/i),
    ).toBeTruthy()
  })

  it('sends a question and shows the answer with its sources', async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.click(screen.getByRole('button', { name: /ask the assistant/i }))
    const input = await screen.findByPlaceholderText(/type your question/i)
    await user.type(input, 'What am I eligible for?')
    await user.click(screen.getByRole('button', { name: /^send$/i }))

    expect(
      await screen.findByText(/eligible for the tuition scheme/i),
    ).toBeTruthy()
    expect(screen.getByText('Tuition Assistance')).toBeTruthy()
    expect(requests).toContain('POST /api/v1/chat')
  })

  it('offers quick replies', async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.click(screen.getByRole('button', { name: /ask the assistant/i }))
    const chip = await screen.findByText('What documents do I need?')
    await user.click(chip)

    await waitFor(() => expect(requests).toContain('POST /api/v1/chat'))
  })

  it('shows an error when the assistant fails', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        if (url.includes('/api/v1/chat') && (init?.method ?? 'GET') === 'POST') {
          return json({ detail: 'Assistant unavailable' }, 500)
        }
        return json({ total: 0, messages: [] })
      }),
    )
    renderPanel()

    await user.click(screen.getByRole('button', { name: /ask the assistant/i }))
    const input = await screen.findByPlaceholderText(/type your question/i)
    await user.type(input, 'hello')
    await user.click(screen.getByRole('button', { name: /^send$/i }))

    expect(await screen.findByRole('alert')).toBeTruthy()
  })
})
