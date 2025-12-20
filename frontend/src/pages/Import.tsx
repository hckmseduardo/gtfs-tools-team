import { Container, Title, Text, Stack } from '@mantine/core'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import GTFSImportWizard from '../components/GTFSImportWizard'

export default function Import() {
  const { t } = useTranslation()
  const navigate = useNavigate()

  return (
    <Container size="xl">
      <Stack gap="lg">
        <div>
          <Title order={1}>{t('import.title')}</Title>
          <Text c="dimmed" mt="sm">
            {t('import.description', 'Import GTFS data from ZIP files into your feeds')}
          </Text>
        </div>

        <GTFSImportWizard
          onComplete={() => navigate('/tasks')}
          onCancel={() => navigate('/feeds')}
        />
      </Stack>
    </Container>
  )
}
