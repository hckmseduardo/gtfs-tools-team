import { useState } from 'react'
import {
  Paper,
  Title,
  Text,
  Stack,
  Group,
  TextInput,
  Button,
  ActionIcon,
  Table,
  Badge,
  Code,
  Tooltip,
  Collapse,
  UnstyledButton,
  Box,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import {
  IconPlus,
  IconTrash,
  IconEdit,
  IconCheck,
  IconX,
  IconChevronDown,
  IconChevronUp,
} from '@tabler/icons-react'
import { useTranslation } from 'react-i18next'

interface CustomFieldsEditorProps {
  customFields: Record<string, any> | null | undefined
  onChange: (fields: Record<string, any>) => void
  entityType: string
  readOnly?: boolean
}

export function CustomFieldsEditor({
  customFields,
  onChange,
  entityType,
  readOnly = false,
}: CustomFieldsEditorProps) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(true)
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')

  const addForm = useForm({
    initialValues: {
      key: '',
      value: '',
    },
    validate: {
      key: (value) => {
        if (!value.trim()) return t('customFields.keyRequired')
        if (customFields && value in customFields) return t('customFields.keyExists')
        return null
      },
      value: (value) => (!value.trim() ? t('customFields.valueRequired') : null),
    },
  })

  const fields = customFields || {}
  const fieldEntries = Object.entries(fields)
  const hasFields = fieldEntries.length > 0

  const handleAdd = (values: { key: string; value: string }) => {
    const newFields = { ...fields, [values.key.trim()]: values.value.trim() }
    onChange(newFields)
    addForm.reset()
  }

  const handleDelete = (key: string) => {
    const newFields = { ...fields }
    delete newFields[key]
    onChange(newFields)
  }

  const handleStartEdit = (key: string, value: any) => {
    setEditingKey(key)
    setEditValue(String(value))
  }

  const handleSaveEdit = () => {
    if (editingKey && editValue.trim()) {
      const newFields = { ...fields, [editingKey]: editValue.trim() }
      onChange(newFields)
    }
    setEditingKey(null)
    setEditValue('')
  }

  const handleCancelEdit = () => {
    setEditingKey(null)
    setEditValue('')
  }

  return (
    <Paper p="md" withBorder>
      <UnstyledButton onClick={() => setExpanded(!expanded)} style={{ width: '100%' }}>
        <Group justify="space-between">
          <Box>
            <Group gap="sm">
              <Title order={5}>{t('customFields.title')}</Title>
              {hasFields && (
                <Badge size="sm" variant="light">
                  {fieldEntries.length}
                </Badge>
              )}
            </Group>
            <Text size="sm" c="dimmed">
              {t('customFields.description', { entityType })}
            </Text>
          </Box>
          {expanded ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
        </Group>
      </UnstyledButton>

      <Collapse in={expanded}>
        <Stack gap="md" mt="md">
          {/* Add new field form */}
          {!readOnly && (
            <Paper p="sm" withBorder bg="gray.0">
              <form onSubmit={addForm.onSubmit(handleAdd)}>
                <Group align="flex-end" gap="sm">
                  <TextInput
                    label={t('customFields.fieldName')}
                    placeholder={t('customFields.fieldNamePlaceholder')}
                    style={{ flex: 1 }}
                    {...addForm.getInputProps('key')}
                  />
                  <TextInput
                    label={t('customFields.fieldValue')}
                    placeholder={t('customFields.fieldValuePlaceholder')}
                    style={{ flex: 1 }}
                    {...addForm.getInputProps('value')}
                  />
                  <Button type="submit" leftSection={<IconPlus size={16} />}>
                    {t('customFields.addField')}
                  </Button>
                </Group>
              </form>
            </Paper>
          )}

          {/* Fields list */}
          {!hasFields ? (
            <Text c="dimmed" ta="center" py="md">
              {t('customFields.noFields')}
            </Text>
          ) : (
            <Table striped highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('customFields.fieldName')}</Table.Th>
                  <Table.Th>{t('customFields.fieldValue')}</Table.Th>
                  {!readOnly && <Table.Th style={{ width: 80 }}>{t('common.actions')}</Table.Th>}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {fieldEntries.map(([key, value]) => (
                  <Table.Tr key={key}>
                    <Table.Td>
                      <Code>{key}</Code>
                    </Table.Td>
                    <Table.Td>
                      {editingKey === key ? (
                        <Group gap="xs">
                          <TextInput
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            size="xs"
                            style={{ flex: 1 }}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleSaveEdit()
                              if (e.key === 'Escape') handleCancelEdit()
                            }}
                            autoFocus
                          />
                          <ActionIcon color="green" variant="subtle" onClick={handleSaveEdit}>
                            <IconCheck size={16} />
                          </ActionIcon>
                          <ActionIcon color="gray" variant="subtle" onClick={handleCancelEdit}>
                            <IconX size={16} />
                          </ActionIcon>
                        </Group>
                      ) : (
                        <Badge variant="light">{String(value)}</Badge>
                      )}
                    </Table.Td>
                    {!readOnly && (
                      <Table.Td>
                        {editingKey !== key && (
                          <Group gap="xs">
                            <Tooltip label={t('common.edit')}>
                              <ActionIcon
                                color="blue"
                                variant="subtle"
                                onClick={() => handleStartEdit(key, value)}
                              >
                                <IconEdit size={16} />
                              </ActionIcon>
                            </Tooltip>
                            <Tooltip label={t('common.delete')}>
                              <ActionIcon
                                color="red"
                                variant="subtle"
                                onClick={() => handleDelete(key)}
                              >
                                <IconTrash size={16} />
                              </ActionIcon>
                            </Tooltip>
                          </Group>
                        )}
                      </Table.Td>
                    )}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Stack>
      </Collapse>
    </Paper>
  )
}

// Read-only display component (for backwards compatibility)
export function CustomFieldsDisplay({
  customFields,
  entityType,
}: {
  customFields: Record<string, any> | null | undefined
  entityType: string
}) {
  return (
    <CustomFieldsEditor
      customFields={customFields}
      onChange={() => {}}
      entityType={entityType}
      readOnly
    />
  )
}
