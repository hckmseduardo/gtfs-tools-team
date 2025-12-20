import { useEffect, useState } from 'react'
import {
    Modal,
    Stack,
    TextInput,
    Group,
    Button,
    LoadingOverlay,
    SimpleGrid,
    Text,
    Alert,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useTranslation } from 'react-i18next'
import { IconInfoCircle } from '@tabler/icons-react'
import { feedApi, type FeedInfo, type FeedInfoCreate, type FeedInfoUpdate } from '../lib/feed-api'
import { notifications } from '@mantine/notifications'

interface FeedInfoModalProps {
    opened: boolean
    onClose: () => void
    feedId: number
    feedName: string
}

export function FeedInfoModal({ opened, onClose, feedId, feedName }: FeedInfoModalProps) {
    const { t } = useTranslation()
    const [loading, setLoading] = useState(false)
    const [fetching, setFetching] = useState(false)
    const [existingInfo, setExistingInfo] = useState<FeedInfo | null>(null)

    const form = useForm<FeedInfoCreate>({
        initialValues: {
            feed_publisher_name: '',
            feed_publisher_url: '',
            feed_lang: '',
            default_lang: '',
            feed_start_date: '',
            feed_end_date: '',
            feed_version: '',
            feed_contact_email: '',
            feed_contact_url: '',
        },
        validate: {
            feed_publisher_name: (value) => (value ? null : t('common.required')),
            feed_publisher_url: (value) => (value ? null : t('common.required')),
            feed_lang: (value) => (value ? null : t('common.required')),
            feed_start_date: (value) =>
                !value || /^\d{8}$/.test(value) ? null : t('validation.invalidDate'),
            feed_end_date: (value) =>
                !value || /^\d{8}$/.test(value) ? null : t('validation.invalidDate'),
            feed_contact_email: (value) =>
                !value || /^\S+@\S+$/.test(value) ? null : t('validation.invalidEmail'),
        },
    })

    useEffect(() => {
        if (opened && feedId) {
            loadFeedInfo()
        }
    }, [opened, feedId])

    const loadFeedInfo = async () => {
        setFetching(true)
        try {
            const info = await feedApi.getFeedInfo(feedId)
            setExistingInfo(info)
            form.setValues({
                feed_publisher_name: info.feed_publisher_name,
                feed_publisher_url: info.feed_publisher_url,
                feed_lang: info.feed_lang,
                default_lang: info.default_lang || '',
                feed_start_date: info.feed_start_date || '',
                feed_end_date: info.feed_end_date || '',
                feed_version: info.feed_version || '',
                feed_contact_email: info.feed_contact_email || '',
                feed_contact_url: info.feed_contact_url || '',
            })
        } catch (error: any) {
            if (error.response?.status === 404) {
                setExistingInfo(null)
                form.reset()
            } else {
                notifications.show({
                    title: t('common.error'),
                    message: t('feedInfo.loadError'),
                    color: 'red',
                })
            }
        } finally {
            setFetching(false)
        }
    }

    const handleSubmit = async (values: FeedInfoCreate) => {
        setLoading(true)
        try {
            // Clean up empty strings to undefined/null
            const cleanValues: any = { ...values }
            Object.keys(cleanValues).forEach((key) => {
                if (cleanValues[key] === '') {
                    cleanValues[key] = null
                }
            })

            if (existingInfo) {
                await feedApi.updateFeedInfo(feedId, cleanValues as FeedInfoUpdate)
                notifications.show({
                    title: t('common.success'),
                    message: t('common.saved'),
                    color: 'green',
                })
            } else {
                await feedApi.createFeedInfo(feedId, cleanValues)
                notifications.show({
                    title: t('common.success'),
                    message: t('common.created'),
                    color: 'green',
                })
            }
            onClose()
        } catch (error: any) {
            let message = t('common.error')
            const detail = error.response?.data?.detail
            if (typeof detail === 'string') {
                message = detail
            } else if (Array.isArray(detail)) {
                // Pydantic validation errors
                message = detail.map((e: any) => `${e.loc.join('.')}: ${e.msg}`).join('\n')
            } else if (detail && typeof detail === 'object') {
                message = JSON.stringify(detail)
            }

            notifications.show({
                title: t('common.error'),
                message,
                color: 'red',
            })
        } finally {
            setLoading(false)
        }
    }

    const handleDelete = async () => {
        if (!confirm(t('common.confirmDelete'))) return

        setLoading(true)
        try {
            await feedApi.deleteFeedInfo(feedId)
            notifications.show({
                title: t('common.success'),
                message: t('common.deleted'),
                color: 'blue',
            })
            onClose()
        } catch (error: any) {
            notifications.show({
                title: t('common.error'),
                message: t('common.error'),
                color: 'red',
            })
        } finally {
            setLoading(false)
        }
    }

    return (
        <Modal
            opened={opened}
            onClose={onClose}
            title={`${t('feedInfo.title')} - ${feedName}`}
            size="lg"
        >
            <form onSubmit={form.onSubmit(handleSubmit)}>
                <Stack gap="md" pos="relative">
                    <LoadingOverlay visible={loading || fetching} />

                    {!existingInfo && !fetching && (
                        <Alert icon={<IconInfoCircle size={16} />} title={t('common.info')} color="blue">
                            {t('feedInfo.noInfo')}
                        </Alert>
                    )}

                    <SimpleGrid cols={2}>
                        <TextInput
                            label={t('feedInfo.publisherName')}
                            placeholder="Example Transit Agency"
                            required
                            {...form.getInputProps('feed_publisher_name')}
                        />
                        <TextInput
                            label={t('feedInfo.publisherUrl')}
                            placeholder="https://example.com"
                            required
                            {...form.getInputProps('feed_publisher_url')}
                        />
                    </SimpleGrid>

                    <SimpleGrid cols={2}>
                        <TextInput
                            label={t('feedInfo.lang')}
                            placeholder="en"
                            required
                            description="ISO 639-1"
                            {...form.getInputProps('feed_lang')}
                        />
                        <TextInput
                            label={t('feedInfo.defaultLang')}
                            placeholder="en"
                            description="ISO 639-1 (Optional)"
                            {...form.getInputProps('default_lang')}
                        />
                    </SimpleGrid>

                    <SimpleGrid cols={2}>
                        <TextInput
                            label={t('feedInfo.startDate')}
                            placeholder="YYYYMMDD"
                            description="Optional"
                            {...form.getInputProps('feed_start_date')}
                        />
                        <TextInput
                            label={t('feedInfo.endDate')}
                            placeholder="YYYYMMDD"
                            description="Optional"
                            {...form.getInputProps('feed_end_date')}
                        />
                    </SimpleGrid>

                    <TextInput
                        label={t('feedInfo.version')}
                        placeholder="v1.0.0"
                        {...form.getInputProps('feed_version')}
                    />

                    <SimpleGrid cols={2}>
                        <TextInput
                            label={t('feedInfo.contactEmail')}
                            placeholder="contact@example.com"
                            {...form.getInputProps('feed_contact_email')}
                        />
                        <TextInput
                            label={t('feedInfo.contactUrl')}
                            placeholder="https://example.com/contact"
                            {...form.getInputProps('feed_contact_url')}
                        />
                    </SimpleGrid>

                    <Text size="xs" c="dimmed">
                        <a
                            href="https://gtfs.org/documentation/schedule/reference/#feed_infotxt"
                            target="_blank"
                            rel="noreferrer"
                        >
                            GTFS Reference: feed_info.txt
                        </a>
                    </Text>

                    <Group justify="space-between" mt="md">
                        {existingInfo ? (
                            <Button color="red" variant="subtle" onClick={handleDelete}>
                                {t('common.delete')}
                            </Button>
                        ) : (
                            <div />
                        )}
                        <Group>
                            <Button variant="light" onClick={onClose}>
                                {t('common.cancel')}
                            </Button>
                            <Button type="submit">{t('common.save')}</Button>
                        </Group>
                    </Group>
                </Stack>
            </form>
        </Modal>
    )
}
