import { describe, expect, it } from 'vitest'

import { en } from './en'
import { hi } from './hi'
import { ta } from './ta'

type Tree = { [key: string]: string | Tree }

function collectKeys(tree: Tree, prefix = ''): string[] {
  return Object.entries(tree).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return typeof value === 'string' ? [path] : collectKeys(value, path)
  })
}

describe('translations', () => {
  const englishKeys = collectKeys(en as unknown as Tree).sort()

  it('has a non-trivial number of strings', () => {
    expect(englishKeys.length).toBeGreaterThan(80)
  })

  it.each([
    ['Tamil', ta],
    ['Hindi', hi],
  ])('%s covers exactly the same keys as English', (_name, translations) => {
    const keys = collectKeys(translations as unknown as Tree).sort()
    expect(keys).toEqual(englishKeys)
  })

  it('leaves no English string empty', () => {
    const empty = collectKeys(en as unknown as Tree).filter((path) => {
      const value = path.split('.').reduce<unknown>((accumulator, part) => {
        if (accumulator && typeof accumulator === 'object') {
          return (accumulator as Record<string, unknown>)[part]
        }
        return undefined
      }, en)
      return typeof value !== 'string' || value.trim() === ''
    })
    expect(empty).toEqual([])
  })

  it('keeps interpolation placeholders in the translations', () => {
    expect(ta.login.otpSubtitle).toContain('{{mobile}}')
    expect(hi.login.resendIn).toContain('{{seconds}}')
    expect(ta.onboarding.stepOf).toContain('{{current}}')
    expect(hi.settings.deleteConfirmBody).toContain('DELETE')
  })
})
