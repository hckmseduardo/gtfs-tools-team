import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import en from './locales/en.json'
import fr from './locales/fr.json'
import pt from './locales/pt.json'
import es from './locales/es.json'
import ar from './locales/ar.json'
import zh from './locales/zh.json'

export const supportedLanguages = [
  { code: 'en', name: 'English', flag: '🇬🇧' },
  { code: 'fr', name: 'Français', flag: '⚜️' },
  { code: 'pt', name: 'Português', flag: '🇧🇷' },
  { code: 'es', name: 'Español', flag: '🇪🇸' },
  { code: 'ar', name: 'العربية', flag: '🇸🇦', dir: 'rtl' },
  { code: 'zh', name: '中文', flag: '🇨🇳' },
] as const

export type LanguageCode = (typeof supportedLanguages)[number]['code']

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      fr: { translation: fr },
      pt: { translation: pt },
      es: { translation: es },
      ar: { translation: ar },
      zh: { translation: zh },
    },
    fallbackLng: 'en',
    supportedLngs: ['en', 'fr', 'pt', 'es', 'ar', 'zh'],
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'gtfs-tools-language',
    },
  })

export default i18n
