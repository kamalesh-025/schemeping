import AutoAwesome from '@mui/icons-material/AutoAwesome'
import ChatBubbleOutline from '@mui/icons-material/ChatBubbleOutline'
import Close from '@mui/icons-material/Close'
import Send from '@mui/icons-material/Send'
import {
  Avatar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  TextField,
  Typography,
} from '@mui/material'
import { useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { ApiError } from '../api/client'
import { chatApi } from '../api/endpoints'
import { AuthContext } from '../auth/context'
import { ErrorBanner } from './ErrorBanner'

interface Turn {
  role: 'user' | 'assistant'
  content: string
  greeting?: boolean
}

const QUICK_REPLIES = [
  'chat.quick.eligible',
  'chat.quick.documents',
  'chat.quick.apply',
  'chat.quick.nearest',
  'chat.quick.explain',
] as const

const BUBBLE_RADIUS = '4px 18px 18px 18px'

function inlineText(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return (
        <Box component="strong" key={`${keyPrefix}-b-${index}`} sx={{ fontWeight: 700 }}>
          {part.slice(2, -2)}
        </Box>
      )
    }
    return <Box component="span" key={`${keyPrefix}-t-${index}`}>{part}</Box>
  })
}

function MessageBody({ text }: { text: string }) {
  const lines = text.split('\n')
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
      {lines.map((line, index) => {
        const trimmed = line.trim()
        if (!trimmed) return <Box key={`gap-${index}`} sx={{ height: 2 }} />
        const bullet = /^[-*•]\s+(.*)$/.exec(trimmed)
        if (bullet) {
          return (
            <Box
              key={`line-${index}`}
              sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}
            >
              <Box component="span" sx={{ lineHeight: 1.55 }}>
                •
              </Box>
              <Box component="span" sx={{ flex: 1 }}>
                {inlineText(bullet[1], `line-${index}`)}
              </Box>
            </Box>
          )
        }
        return (
          <Box component="p" key={`line-${index}`} sx={{ m: 0 }}>
            {inlineText(trimmed, `line-${index}`)}
          </Box>
        )
      })}
    </Box>
  )
}

/**
 * The assistant: a floating button that opens a large, readable chat sheet.
 *
 * Accessibility rules from AGENTS.md 13: 48px tap targets, icon + text labels,
 * plain language. The assistant answers from verified scheme records and can
 * help with general questions, so the panel always shows the sources it used.
 */
export function ChatPanel() {
  const { t, i18n } = useTranslation()
  const auth = useContext(AuthContext)
  const [open, setOpen] = useState(false)
  const [turns, setTurns] = useState<Turn[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [sources, setSources] = useState<string[]>([])
  const [lastQuestion, setLastQuestion] = useState('')
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const firstName = auth?.profile?.name?.trim().split(/\s+/)[0] ?? ''
  const greeting = firstName
    ? t('chat.greetingNamed', { name: firstName })
    : t('chat.greeting')

  useEffect(() => {
    if (open) {
      setError(null)
      setTurns((current) =>
        current.length > 0
          ? current
          : [{ role: 'assistant', content: '', greeting: true }],
      )
      void loadHistory()
      const timer = window.setTimeout(() => inputRef.current?.focus(), 120)
      return () => window.clearTimeout(timer)
    }
    return undefined
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    const node = bottomRef.current
    // Not every environment implements scrollIntoView (jsdom, old browsers).
    if (node && typeof node.scrollIntoView === 'function') {
      node.scrollIntoView({ block: 'end', behavior: 'smooth' })
    }
  }, [turns, busy])

  const loadHistory = useCallback(async () => {
    try {
      const history = await chatApi.history(30)
      setTurns(
        history.messages.length > 0
          ? history.messages.map((message) => ({
              role: message.role,
              content: message.content,
            }))
          : [{ role: 'assistant', content: '', greeting: true }],
      )
    } catch {
      // A missing history is not an error worth showing; still say hello.
      setTurns([{ role: 'assistant', content: '', greeting: true }])
    }
  }, [])

  const send = useCallback(
    async (question: string, appendUser = true) => {
      const text = question.trim()
      if (!text || busy) return
      const language = (i18n.language || 'en').slice(0, 2)
      if (appendUser) {
        setDraft('')
        setTurns((current) => [...current, { role: 'user', content: text }])
      }
      setLastQuestion(text)
      setError(null)
      setSources([])
      setBusy(true)
      try {
        const answer = await chatApi.ask(text, language as never)
        setTurns((current) => [
          ...current,
          { role: 'assistant', content: answer.answer },
        ])
        setSources(answer.sources.map((source) => source.name))
      } catch (caught) {
        setError(caught)
      } finally {
        setBusy(false)
      }
    },
    [busy, i18n.language],
  )

  if (!open) {
    return (
      <Box
        sx={{
          position: 'fixed',
          right: { xs: 12, md: 24 },
          bottom: { xs: 88, md: 24 },
          zIndex: 1200,
        }}
      >
        <Button
          variant="contained"
          color="primary"
          startIcon={<ChatBubbleOutline />}
          onClick={() => setOpen(true)}
          sx={{
            minHeight: 56,
            borderRadius: 28,
            px: 3,
            fontSize: '1rem',
            boxShadow: '0 6px 18px lightgray',
            '&:hover': { boxShadow: '0 8px 22px darkgray' },
          }}
        >
          {t('chat.open')}
        </Button>
      </Box>
    )
  }

  return (
    <Dialog
      open
      onClose={() => setOpen(false)}
      aria-labelledby="chat-heading"
      fullWidth
      maxWidth="sm"
      sx={{
        '& .MuiDialog-container': { alignItems: { xs: 'flex-end', sm: 'center' } },
        '& .MuiDialog-paper': {
          width: { xs: '100%', sm: 'min(600px, calc(100% - 48px))' },
          height: { xs: '88dvh', sm: '74dvh' },
          maxHeight: '92dvh',
          m: 0,
          borderRadius: { xs: '18px 18px 0 0', sm: '18px' },
          overflow: 'hidden',
        },
      }}
    >
      <DialogTitle
        id="chat-heading"
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.5,
          p: 2,
          background: 'linear-gradient(135deg, navy, darkgreen)',
          color: 'white',
        }}
      >
        <Avatar sx={{ backgroundColor: 'white', color: 'navy', width: 40, height: 40 }}>
          <AutoAwesome fontSize="small" />
        </Avatar>
        <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <Typography
            variant="h3"
            component="span"
            sx={{ display: 'block', color: 'white', fontSize: '1.1rem', lineHeight: 1.3 }}
          >
            {t('chat.title')}
          </Typography>
          <Typography
            component="span"
            sx={{ display: 'block', color: 'honeydew', fontSize: '0.95rem' }}
          >
            {t('chat.subtitle')}
          </Typography>
        </Box>
        <IconButton
          aria-label={t('chat.close')}
          onClick={() => setOpen(false)}
          sx={{ color: 'white' }}
        >
          <Close />
        </IconButton>
      </DialogTitle>

      <DialogContent
        aria-live="polite"
        sx={{
          flex: 1,
          minHeight: 0,
          overflowY: 'auto',
          p: 2,
          backgroundColor: 'whitesmoke',
          display: 'flex',
          flexDirection: 'column',
          gap: 1.5,
        }}
      >
        {turns.map((turn, index) => {
          const content = turn.greeting ? greeting : turn.content
          const isUser = turn.role === 'user'
          return (
            <Box
              key={`${turn.role}-${index}`}
              sx={{
                display: 'flex',
                gap: 1,
                alignItems: 'flex-end',
                alignSelf: isUser ? 'flex-end' : 'flex-start',
                maxWidth: '92%',
                flexDirection: isUser ? 'row-reverse' : 'row',
              }}
            >
              {!isUser ? (
                <Avatar
                  sx={{
                    width: 30,
                    height: 30,
                    backgroundColor: 'navy',
                    color: 'white',
                    flex: '0 0 auto',
                  }}
                >
                  <AutoAwesome sx={{ fontSize: 17 }} />
                </Avatar>
              ) : null}
              <Box
                sx={{
                  px: 2,
                  py: 1.25,
                  borderRadius: isUser ? '18px 4px 18px 18px' : BUBBLE_RADIUS,
                  backgroundColor: isUser ? 'navy' : 'white',
                  color: isUser ? 'white' : 'darkslategray',
                  border: isUser ? 0 : '1px solid gainsboro',
                  boxShadow: isUser ? 'none' : '0 1px 3px lightgray',
                  fontSize: '1.0625rem',
                  lineHeight: 1.55,
                  overflowWrap: 'anywhere',
                }}
              >
                <MessageBody text={content} />
              </Box>
            </Box>
          )
        })}

        {sources.length > 0 ? (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, pl: 5 }}>
            <Typography
              variant="caption"
              sx={{ alignSelf: 'center', color: 'dimgray', fontWeight: 600 }}
            >
              {t('chat.sources')}:
            </Typography>
            {sources.map((name) => (
              <Chip
                key={name}
                label={name}
                size="small"
                variant="outlined"
                sx={{ backgroundColor: 'white' }}
              />
            ))}
          </Box>
        ) : null}

        {busy ? (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, pl: 5 }}>
            <Box className="chat-typing" aria-hidden="true">
              <Box component="span" />
              <Box component="span" />
              <Box component="span" />
            </Box>
            <Typography variant="body2" color="text.secondary">
              {t('chat.typing')}
            </Typography>
          </Box>
        ) : null}

        <ErrorBanner
          error={error}
          onRetry={lastQuestion ? () => void send(lastQuestion, false) : undefined}
        />
        {error instanceof ApiError && error.status === 429 ? (
          <Typography variant="caption" color="error">
            {t('chat.rateLimited')}
          </Typography>
        ) : null}
        <div ref={bottomRef} />
      </DialogContent>

      <Box sx={{ p: 1.5, borderTop: '1px solid gainsboro', backgroundColor: 'white' }}>
        <Box
          sx={{
            display: 'flex',
            gap: 1,
            mb: 1.25,
            overflowX: 'auto',
            pb: 0.5,
            '&::-webkit-scrollbar': { height: 4 },
          }}
        >
          {QUICK_REPLIES.map((key) => (
            <Chip
              key={key}
              label={t(key)}
              onClick={() => void send(t(key) as string)}
              disabled={busy}
              sx={{ minHeight: 38, flex: '0 0 auto', backgroundColor: 'aliceblue' }}
            />
          ))}
        </Box>
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end' }}>
          <TextField
            inputRef={inputRef}
            fullWidth
            multiline
            maxRows={4}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void send(draft)
              }
            }}
            placeholder={t('chat.placeholder')}
            inputProps={{ 'aria-label': t('chat.placeholder'), maxLength: 1000 }}
            sx={{
              '& .MuiOutlinedInput-root': {
                borderRadius: 6,
                backgroundColor: 'whitesmoke',
                '& fieldset': { borderColor: 'gainsboro' },
              },
            }}
          />
          <IconButton
            aria-label={t('chat.send')}
            onClick={() => void send(draft)}
            disabled={busy || draft.trim().length === 0}
            color="primary"
            sx={{
              width: 48,
              height: 48,
              flex: '0 0 auto',
              backgroundColor: busy || !draft.trim() ? 'gainsboro' : 'navy',
              color: 'white',
              '&:hover': { backgroundColor: 'midnightblue' },
              '&.Mui-disabled': { backgroundColor: 'gainsboro', color: 'gray' },
            }}
          >
            {busy ? <CircularProgress size={20} sx={{ color: 'navy' }} /> : <Send />}
          </IconButton>
        </Box>
        <Typography
          variant="caption"
          sx={{ display: 'block', mt: 0.75, color: 'gray', textAlign: 'center' }}
        >
          {t('chat.disclaimer')}
        </Typography>
      </Box>
    </Dialog>
  )
}
