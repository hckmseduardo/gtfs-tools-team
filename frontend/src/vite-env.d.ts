/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_WS_URL: string
  readonly VITE_AZURE_AD_CLIENT_ID: string
  readonly VITE_AZURE_AD_TENANT_ID: string
  readonly VITE_AZURE_AD_AUTHORITY: string
  readonly VITE_MAPBOX_TOKEN: string
  readonly VITE_ENVIRONMENT: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
