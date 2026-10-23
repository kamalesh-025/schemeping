/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Absolute API root, e.g. https://api.example.com/api/v1. Leave unset to use
   * `/api/v1` on the same origin (Vite proxy in development, Caddy in
   * production, or a Vercel rewrite to the API host).
   */
  readonly VITE_API_BASE_URL?: string
}
