/**
 * Colour-name-aware replacement for MUI's `@mui/system/colorManipulator`.
 *
 * SchemePing's styling rule is that all HTML, CSS, and theme colours use CSS
 * colour names (navy, seagreen, whitesmoke, ...) rather than hex or rgb values.
 * MUI's built-in helpers only parse hex/rgb/hsl, so this module implements the
 * same public surface on top of CSS `color-mix()`, which blends named colours
 * natively in the browser.
 *
 * It is installed through a Vite resolve alias, so internal MUI calls such as
 * `alpha(theme.palette.primary.main, 0.08)` transparently use this version.
 * The `private_safe*` helpers MUI imports are provided with matching behaviour.
 *
 * Known limitation: `colorChannel()` cannot expand a named colour into
 * "r g b" channels. It is only used when CSS theme variables are enabled, which
 * this app does not do (MUI then uses `alpha()` instead).
 */

type RgbaColor = { type: string; values: Array<number | string> }
type Color = string
type Channels = [number, number, number, number]

/**
 * CSS colour names used by the app, plus the handful MUI needs internally.
 * Names cannot be expanded to channels by the browser, so they are listed here
 * for the luminance maths that drives contrast decisions.
 */
const NAMED_RGB: Record<string, [number, number, number]> = {
  black: [0, 0, 0],
  navy: [0, 0, 128],
  darkred: [139, 0, 0],
  firebrick: [178, 34, 34],
  indianred: [205, 92, 92],
  orangered: [255, 69, 0],
  darkorange: [255, 140, 0],
  orange: [255, 165, 0],
  saddlebrown: [139, 69, 19],
  seagreen: [46, 139, 87],
  forestgreen: [34, 139, 34],
  mediumseagreen: [60, 179, 113],
  darkgreen: [0, 100, 0],
  darkseagreen: [143, 188, 143],
  darkcyan: [0, 139, 139],
  lightseagreen: [32, 178, 170],
  darkslategray: [47, 79, 79],
  darkslategrey: [47, 79, 79],
  steelblue: [70, 130, 180],
  skyblue: [135, 206, 235],
  royalblue: [65, 105, 225],
  midnightblue: [25, 25, 112],
  darkslateblue: [72, 61, 139],
  dimgray: [105, 105, 105],
  gray: [128, 128, 128],
  grey: [128, 128, 128],
  lightgray: [211, 211, 211],
  lightgrey: [211, 211, 211],
  darkgray: [169, 169, 169],
  darkgrey: [169, 169, 169],
  gainsboro: [220, 220, 220],
  palegreen: [152, 251, 152],
  honeydew: [240, 255, 240],
  mintcream: [245, 255, 250],
  whitesmoke: [245, 245, 245],
  floralwhite: [255, 250, 240],
  seashell: [255, 245, 238],
  ivory: [255, 255, 240],
  snow: [255, 250, 250],
  white: [255, 255, 255],
  transparent: [0, 0, 0],
}

function clamp(value: number): number {
  return Math.min(1, Math.max(0, value))
}

function percent(value: number): number {
  return Math.round(clamp(value) * 100)
}

function mix(color: Color, coefficient: number, toward: 'white' | 'black' | 'transparent'): string {
  if (toward === 'transparent') {
    return `color-mix(in srgb, ${color} ${percent(coefficient)}%, transparent)`
  }
  return `color-mix(in srgb, ${color} ${percent(1 - clamp(coefficient))}%, ${toward})`
}

function parseChannel(token: string): number {
  const value = token.trim()
  if (value.endsWith('%')) return Math.round((Number(value.slice(0, -1)) / 100) * 255)
  return Math.round(Number(value))
}

/** Parses hex, rgb(), rgba(), hsl() and hsla() into r, g, b, a (0-255 / 0-1). */
function parseColor(input: Color): Channels | null {
  const color = input.trim().toLowerCase()

  const named = NAMED_RGB[color]
  if (named) return [named[0], named[1], named[2], 1]

  if (color.startsWith('#')) {
    const hex = color.slice(1)
    const expand = (part: string) => Number.parseInt(part.repeat(2), 16)
    if (hex.length === 3 || hex.length === 4) {
      return [
        expand(hex[0]),
        expand(hex[1]),
        expand(hex[2]),
        hex.length === 4 ? expand(hex[3]) / 255 : 1,
      ]
    }
    if (hex.length === 6 || hex.length === 8) {
      const part = (start: number) => Number.parseInt(hex.slice(start, start + 2), 16)
      return [part(0), part(2), part(4), hex.length === 8 ? part(6) / 255 : 1]
    }
    return null
  }

  const functional = /^([a-z]+)\(([^)]+)\)$/.exec(color)
  if (!functional) return null

  const [, name, body] = functional
  const parts = body.replace(/\//g, ' ').split(/[\s,]+/).filter(Boolean)

  if (name === 'rgb' || name === 'rgba') {
    if (parts.length < 3) return null
    const alpha = parts.length > 3 ? parts[3] : '1'
    return [
      parseChannel(parts[0]),
      parseChannel(parts[1]),
      parseChannel(parts[2]),
      alpha.endsWith('%') ? Number(alpha.slice(0, -1)) / 100 : Number(alpha),
    ]
  }

  if (name === 'hsl' || name === 'hsla') {
    const rgb = hslToRgb(color)
    const alpha = parts.length > 3 ? parts[3] : '1'
    return [
      Number(rgb.values[0]),
      Number(rgb.values[1]),
      Number(rgb.values[2]),
      alpha.endsWith('%') ? Number(alpha.slice(0, -1)) / 100 : Number(alpha),
    ]
  }

  return null
}

export function alpha(color: Color, value: number): string {
  if (value >= 1) return color
  const key = color.trim().toLowerCase()
  if (key === 'transparent') return 'transparent'
  if (!NAMED_RGB[key]) {
    const channels = parseColor(color)
    if (channels) {
      return `rgba(${channels[0]}, ${channels[1]}, ${channels[2]}, ${clamp(value)})`
    }
  }
  return mix(color, value, 'transparent')
}

export function private_safeAlpha(color: Color, value: number, _warning?: string): string {
  return alpha(color, value)
}

export function lighten(color: Color, coefficient: number): string {
  return mix(color, coefficient, 'white')
}

export function private_safeLighten(color: Color, coefficient: number, _warning?: string): string {
  return lighten(color, coefficient)
}

export function darken(color: Color, coefficient: number): string {
  return mix(color, coefficient, 'black')
}

export function private_safeDarken(color: Color, coefficient: number, _warning?: string): string {
  return darken(color, coefficient)
}

export function emphasize(color: Color, coefficient = 0.15): string {
  return coefficient > 0 ? darken(color, coefficient) : lighten(color, -coefficient)
}

export function private_safeEmphasize(
  color: Color,
  coefficient = 0.15,
  _warning?: string,
): string {
  return emphasize(color, coefficient)
}

export function mixColor(background: Color, overlay: Color, opacity: number): string {
  return `color-mix(in srgb, ${overlay} ${percent(opacity)}%, ${background})`
}

export function blend(background: Color, overlay: Color, opacity: number, _gamma = 1): string {
  return mixColor(background, overlay, opacity)
}

/**
 * A named colour cannot be expanded into channels, so this returns the colour
 * unchanged. It is only reached when CSS theme variables are enabled.
 */
export function colorChannel(color: Color): string {
  return color
}

export function private_safeColorChannel(color: Color, _warning?: string): string {
  return colorChannel(color)
}

export function getLuminance(color: Color): number {
  const channels = parseColor(color)
  if (!channels) {
    // Unknown colour names cannot be measured; every palette entry in this app
    // sets an explicit contrastText, so this is only a safety net.
    return 0.5
  }
  const [red, green, blue] = channels.map((channel) => {
    const value = channel / 255
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
  return Number((0.2126 * red + 0.7152 * green + 0.0722 * blue).toFixed(3))
}

export function getContrastRatio(foreground: Color, background: Color): number {
  const first = getLuminance(foreground)
  const second = getLuminance(background)
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05)
}

/** Minimal HSL support, kept for API completeness. */
export function hslToRgb(color: Color): RgbaColor {
  const match = /^hsla?\(\s*([\d.]+)\s*[, ]\s*([\d.]+)%\s*[, ]\s*([\d.]+)%\s*(?:[,/]\s*([\d.]+%?))?\s*\)$/i.exec(
    color.trim(),
  )
  if (!match) return { type: 'rgb', values: [0, 0, 0] }

  const hue = ((Number(match[1]) % 360) + 360) % 360
  const saturation = Number(match[2]) / 100
  const lightness = Number(match[3]) / 100
  const chroma = (1 - Math.abs(2 * lightness - 1)) * saturation
  const secondary = chroma * (1 - Math.abs(((hue / 60) % 2) - 1))
  const offset = lightness - chroma / 2

  let rgb: [number, number, number]
  if (hue < 60) rgb = [chroma, secondary, 0]
  else if (hue < 120) rgb = [secondary, chroma, 0]
  else if (hue < 180) rgb = [0, chroma, secondary]
  else if (hue < 240) rgb = [0, secondary, chroma]
  else if (hue < 300) rgb = [secondary, 0, chroma]
  else rgb = [chroma, 0, secondary]

  return {
    type: 'rgb',
    values: rgb.map((channel) => Math.round((channel + offset) * 255)),
  }
}

export function hexToRgb(color: Color): RgbaColor {
  return decomposeColor(color)
}

export function decomposeColor(color: Color): RgbaColor {
  const channels = parseColor(color)
  if (channels) {
    return { type: channels[3] === 1 ? 'rgb' : 'rgba', values: [channels[0], channels[1], channels[2]] }
  }
  return { type: 'named', values: [color.trim()] }
}

export function recomposeColor(color: RgbaColor): string {
  if (color.type === 'named') return String(color.values[0])
  return `${color.type}(${color.values.join(', ')})`
}

export function rgbToHex(color: Color | RgbaColor): string {
  return typeof color === 'string' ? color : recomposeColor(color)
}

export default {
  alpha,
  blend,
  colorChannel,
  darken,
  decomposeColor,
  emphasize,
  getContrastRatio,
  getLuminance,
  hexToRgb,
  hslToRgb,
  lighten,
  mixColor,
  private_safeAlpha,
  private_safeColorChannel,
  private_safeDarken,
  private_safeEmphasize,
  private_safeLighten,
  recomposeColor,
  rgbToHex,
}
