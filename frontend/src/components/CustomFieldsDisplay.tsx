import { Paper, Title, Text, Stack, Group, Code, Badge } from '@mantine/core'

interface CustomFieldsDisplayProps {
  customFields: Record<string, any> | null | undefined
  entityType: string
}

export function CustomFieldsDisplay({ customFields, entityType }: CustomFieldsDisplayProps) {
  // Don't render if no custom fields
  if (!customFields || Object.keys(customFields).length === 0) {
    return null
  }

  return (
    <Paper p="md" withBorder>
      <Title order={5}>Custom Fields</Title>
      <Text size="sm" c="dimmed">
        Additional fields specific to this {entityType}
      </Text>
      <Stack gap="xs" mt="md">
        {Object.entries(customFields).map(([key, value]) => (
          <Group key={key} justify="space-between">
            <Code>{key}</Code>
            <Badge variant="light">{String(value)}</Badge>
          </Group>
        ))}
      </Stack>
    </Paper>
  )
}
