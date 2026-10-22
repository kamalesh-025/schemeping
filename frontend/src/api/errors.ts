import { ApiError } from './client'

/** Turns an unknown thrown value into a translation key or a plain message. */
export function messageForError(error: unknown): string {
  if (error instanceof ApiError) {
    // A component may deliberately throw a translation key (for example a
    // wrong password on the sign-in form); it wins over the status default.
    if (error.message.startsWith('errors.')) return error.message
    if (error.status === 0) return 'errors.network'
    if (error.status === 401) return 'errors.unauthorized'
    if (error.message) return error.message
  }
  return 'errors.generic'
}
