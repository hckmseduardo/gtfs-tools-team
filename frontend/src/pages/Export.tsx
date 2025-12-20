import { useState } from 'react'
import {
  Container,
  Title,
  Text,
  Stack,
  Paper,
} from '@mantine/core'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import GTFSExportWizard from '../components/GTFSExportWizard'

export default function Export() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [showSuccess, setShowSuccess] = useState(false)

  const handleComplete = () => {
    setShowSuccess(true)
    // Optionally navigate to task manager or stay on page
  }

  const handleCancel = () => {
    navigate(-1)
  }

  return (
    <Container size="xl">
      <Stack gap="lg">
        <div>
          <Title order={1}>{t('export.title', 'Export GTFS')}</Title>
          <Text c="dimmed" mt="sm">
            {t('export.pageDescription', 'Export your GTFS data to a ZIP file. The system will validate the export before download.')}
          </Text>
        </div>

        <Paper withBorder shadow="sm" radius="md">
          <GTFSExportWizard
            onComplete={handleComplete}
            onCancel={handleCancel}
          />
        </Paper>
      </Stack>
    </Container>
  )
}
