import { describe, expect, it } from 'vitest'

import {
  alpha,
  darken,
  emphasize,
  getContrastRatio,
  lighten,
  private_safeAlpha,
  private_safeColorChannel,
} from './colorManipulator'

describe('colorManipulator', () => {
  it('expresses alpha for a named colour with color-mix', () => {
    expect(alpha('navy', 0.08)).toBe('color-mix(in srgb, navy 8%, transparent)')
  })

  it('returns the colour unchanged when alpha is fully opaque', () => {
    expect(alpha('navy', 1)).toBe('navy')
  })

  it('lightens and darkens toward white and black', () => {
    expect(lighten('navy', 0.5)).toBe('color-mix(in srgb, navy 50%, white)')
    expect(darken('seagreen', 0.25)).toBe('color-mix(in srgb, seagreen 75%, black)')
  })

  it('emphasises by darkening when the coefficient is positive', () => {
    expect(emphasize('gray', 0.2)).toBe('color-mix(in srgb, gray 80%, black)')
    expect(emphasize('gray', -0.2)).toBe('color-mix(in srgb, gray 80%, white)')
  })

  it('never emits hex or rgb values', () => {
    const values = [alpha('navy', 0.5), lighten('navy', 0.4), darken('navy', 0.4)]
    for (const value of values) {
      expect(value).not.toMatch(/#[0-9a-f]{3,8}\b/i)
      expect(value).not.toMatch(/\brgba?\(/i)
    }
  })

  it('provides the private-safe helpers MUI imports', () => {
    expect(private_safeAlpha('navy', 0.5, 'warning')).toBe(
      'color-mix(in srgb, navy 50%, transparent)',
    )
    expect(private_safeColorChannel('navy')).toBe('navy')
  })

  it('computes a plausible contrast ratio for named colours', () => {
    expect(getContrastRatio('black', 'white')).toBeGreaterThan(10)
    expect(getContrastRatio('navy', 'white')).toBeGreaterThan(1)
  })

  it('measures the government-green palette used by the theme', () => {
    expect(getContrastRatio('darkgreen', 'white')).toBeGreaterThan(7)
    expect(getContrastRatio('saddlebrown', 'white')).toBeGreaterThan(4.5)
    expect(alpha('forestgreen', 0.1)).toBe(
      'color-mix(in srgb, forestgreen 10%, transparent)',
    )
  })
})
