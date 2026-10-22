import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import { en } from './en'
import { hi } from './hi'
import { ta } from './ta'

export const SUPPORTED_LANGUAGES = [
  { code: 'en', nativeName: 'English' },
  { code: 'ta', nativeName: 'தமிழ்' },
  { code: 'hi', nativeName: 'हिन्दी' },
] as const

export type LanguageCode = (typeof SUPPORTED_LANGUAGES)[number]['code']

const STORAGE_KEY = 'schemeping.language'

export function storedLanguage(): LanguageCode {
  const value = localStorage.getItem(STORAGE_KEY)
  if (value === 'en' || value === 'ta' || value === 'hi') return value
  const browser = navigator.language.slice(0, 2)
  if (browser === 'ta' || browser === 'hi') return browser
  return 'en'
}

export function persistLanguage(code: LanguageCode): void {
  localStorage.setItem(STORAGE_KEY, code)
  document.documentElement.lang = code
}

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    ta: { translation: ta },
    hi: { translation: hi },
  },
  lng: storedLanguage(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
  returnNull: false,
})

document.documentElement.lang = i18n.language

export default i18n
