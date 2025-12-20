import { Menu, UnstyledButton, Group, Text } from '@mantine/core'
import { IconLanguage, IconCheck } from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'
import { supportedLanguages, type LanguageCode } from '../i18n'

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation()
  const currentLanguage = i18n.language as LanguageCode

  const currentLang = supportedLanguages.find(
    (lang) => lang.code === currentLanguage || currentLanguage.startsWith(lang.code)
  ) || supportedLanguages[0]

  const handleLanguageChange = (langCode: LanguageCode) => {
    i18n.changeLanguage(langCode)
  }

  return (
    <Menu shadow="md" width={200} position="bottom-end" zIndex={9999}>
      <Menu.Target>
        <UnstyledButton
          style={{
            padding: '8px 12px',
            borderRadius: '4px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <IconLanguage size={18} />
          <Text size="sm">{currentLang.flag} {currentLang.name}</Text>
        </UnstyledButton>
      </Menu.Target>

      <Menu.Dropdown>
        <Menu.Label>{t('settings.language')}</Menu.Label>
        {supportedLanguages.map((lang) => (
          <Menu.Item
            key={lang.code}
            onClick={() => handleLanguageChange(lang.code)}
            rightSection={
              currentLang.code === lang.code ? <IconCheck size={14} /> : null
            }
          >
            <Group gap="xs">
              <Text>{lang.flag}</Text>
              <Text>{lang.name}</Text>
            </Group>
          </Menu.Item>
        ))}
      </Menu.Dropdown>
    </Menu>
  )
}
