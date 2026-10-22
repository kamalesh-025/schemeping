/**
 * Thin wrapper around the MSG91 OTP widget (web SDK, custom UI).
 *
 * Why this exists: Indian A2P SMS needs DLT registration for *your own* sender
 * and template. The OTP widget sends and verifies the code with MSG91's own
 * DLT-registered sender and default template, so no DLT registration is
 * required. MSG91 therefore owns the OTP itself and hands back an access token
 * after a successful verification; the backend exchanges that token for the
 * mobile number it actually verified (see POST /auth/otp/widget/verify).
 *
 * Rules this file keeps:
 * - the OTP never reaches SchemePing code;
 * - the mobile number is never trusted from the client, only from the backend;
 * - the public widget token is used here, never the MSG91 auth key.
 */

import { ApiError } from '../api/client'

const SCRIPT_SRC = 'https://verify.msg91.com/otp-provider.js'
const SCRIPT_ATTRIBUTE = 'data-msg91-widget'

/** Container the widget renders its reCAPTCHA into (when enabled). */
export const WIDGET_CAPTCHA_ELEMENT_ID = 'msg91-widget-captcha'

type WidgetCallback = (data: unknown) => void

declare global {
  interface Window {
    initSendOTP?: (config: Record<string, unknown>) => void
    sendOtp?: (identifier: string, success?: WidgetCallback, failure?: WidgetCallback) => void
    verifyOtp?: (
      otp: string | number,
      success?: WidgetCallback,
      failure?: WidgetCallback,
      requestId?: string,
    ) => void
  }
}

let initialisation: Promise<void> | null = null

function widgetError(key: string): ApiError {
  // ApiError + an i18n key lets ErrorBanner translate it like any other error.
  return new ApiError(400, key)
}

/** Loads the SDK and calls ``initSendOTP`` once. Safe to call repeatedly. */
export function loadMsg91Widget(widgetId: string, tokenAuth: string): Promise<void> {
  if (initialisation) return initialisation

  initialisation = new Promise<void>((resolve, reject) => {
    const initialise = () => {
      if (typeof window.initSendOTP !== 'function') {
        reject(widgetError('errors.otpWidgetUnavailable'))
        return
      }
      try {
        window.initSendOTP({
          widgetId,
          tokenAuth,
          // Render no MSG91 UI: we drive sendOtp/verifyOtp from our own form.
          exposeMethods: true,
          captchaRenderId: WIDGET_CAPTCHA_ELEMENT_ID,
          success: () => {},
          failure: () => {},
        })
      } catch {
        reject(widgetError('errors.otpWidgetUnavailable'))
        return
      }
      resolve()
    }

    if (document.querySelector(`script[${SCRIPT_ATTRIBUTE}]`)) {
      initialise()
      return
    }

    const script = document.createElement('script')
    script.src = SCRIPT_SRC
    script.async = true
    script.setAttribute(SCRIPT_ATTRIBUTE, 'true')
    script.onload = initialise
    script.onerror = () => reject(widgetError('errors.otpWidgetUnavailable'))
    document.head.appendChild(script)
  })

  // A failed load must be retryable on the next attempt.
  initialisation = initialisation.catch((error: unknown) => {
    initialisation = null
    throw error
  })

  return initialisation
}

/** MSG91 returns the access token under one of these keys. */
const TOKEN_KEYS = ['access-token', 'accessToken', 'access_token', 'token', 'message']

function looksLikeToken(value: string): boolean {
  return value.length >= 20 && !/\s/.test(value)
}

export function extractAccessToken(data: unknown): string | null {
  if (typeof data === 'string') return looksLikeToken(data) ? data : null
  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>
    for (const key of TOKEN_KEYS) {
      const value = record[key]
      if (typeof value === 'string' && looksLikeToken(value)) return value
    }
  }
  return null
}

function reasonFor(failure: unknown, fallback: string): string {
  if (typeof failure === 'string' && failure) return failure
  if (failure && typeof failure === 'object') {
    const record = failure as Record<string, unknown>
    const message = record.message ?? record.error
    if (typeof message === 'string' && message) return message
  }
  return fallback
}

/** Asks MSG91 to send a code. The identifier needs the country code. */
export function sendWidgetOtp(mobile: string): Promise<void> {
  return new Promise<void>((resolve, reject) => {
    if (typeof window.sendOtp !== 'function') {
      reject(widgetError('errors.otpWidgetUnavailable'))
      return
    }
    window.sendOtp(
      `91${mobile}`,
      () => resolve(),
      (failure) => {
        console.error('MSG91 widget send failed:', reasonFor(failure, 'unknown'))
        reject(widgetError('errors.otpSendFailed'))
      },
    )
  })
}

/** Verifies the typed code with MSG91 and returns its access token. */
export function verifyWidgetOtp(otp: string): Promise<string> {
  return new Promise<string>((resolve, reject) => {
    if (typeof window.verifyOtp !== 'function') {
      reject(widgetError('errors.otpWidgetUnavailable'))
      return
    }
    window.verifyOtp(
      otp,
      (data) => {
        const token = extractAccessToken(data)
        if (token) resolve(token)
        else reject(widgetError('errors.otpVerifyFailed'))
      },
      (failure) => {
        console.error('MSG91 widget verify failed:', reasonFor(failure, 'unknown'))
        reject(widgetError('errors.otpVerifyFailed'))
      },
    )
  })
}
