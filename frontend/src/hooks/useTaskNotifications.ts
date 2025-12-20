/**
 * Global hook for tracking task completion notifications
 *
 * This hook monitors active tasks (pending/running) and shows notifications
 * only when they complete or fail AFTER the hook was initialized.
 */

import { useEffect, useRef, useCallback } from 'react'
import { notifications } from '@mantine/notifications'
import { tasksApi, TaskStatus } from '../lib/tasks-api'
import { useTranslation } from 'react-i18next'

/**
 * Hook to monitor tasks and show completion notifications
 */
export function useTaskNotifications() {
  const { t } = useTranslation()
  const intervalRef = useRef<NodeJS.Timeout | null>(null)

  // Track tasks that were active (pending/running) when we started monitoring
  const activeTasksRef = useRef<Map<number, TaskStatus>>(new Map())
  const initializedRef = useRef(false)
  const notifiedTasksRef = useRef<Set<number>>(new Set())
  const lastCheckRef = useRef<Date>(new Date())

  const checkTasks = useCallback(async () => {
    try {
      // Get recent tasks (pending, running, and recently completed)
      const response = await tasksApi.list({ limit: 50 })

      const now = new Date()

      if (!initializedRef.current) {
        // First run: capture all currently active tasks and mark existing completed tasks
        for (const task of response.items) {
          if (task.status === TaskStatus.PENDING || task.status === TaskStatus.RUNNING) {
            activeTasksRef.current.set(task.id, task.status)
          } else {
            // Mark already-completed tasks so we don't notify about them
            notifiedTasksRef.current.add(task.id)
          }
        }
        initializedRef.current = true
        lastCheckRef.current = now
        return
      }

      // Subsequent runs: check for status changes
      for (const task of response.items) {
        // Skip if we've already notified about this task
        if (notifiedTasksRef.current.has(task.id)) continue

        // Check if task was previously tracked as active
        const wasActive = activeTasksRef.current.has(task.id)

        // Check if task was created recently (since last check + buffer for timing)
        const taskCreatedAt = new Date(task.created_at)
        const isRecentlyCreated = taskCreatedAt.getTime() > (lastCheckRef.current.getTime() - 1000) // 1s buffer

        // Track new active tasks for future monitoring
        if (task.status === TaskStatus.PENDING || task.status === TaskStatus.RUNNING) {
          activeTasksRef.current.set(task.id, task.status)
          continue
        }

        // For completed/failed tasks, only notify if:
        // 1. It was previously tracked as active, OR
        // 2. It was created recently (completed quickly before we could track it)
        if (!wasActive && !isRecentlyCreated) {
          continue
        }

        // Task was active and has now completed or failed
        if (task.status === TaskStatus.COMPLETED) {
          notifiedTasksRef.current.add(task.id)
          activeTasksRef.current.delete(task.id)

          notifications.show({
            title: t('tasks.completed'),
            message: `${task.task_name} ${t('tasks.completedSuccessfully')}`,
            color: 'green',
            autoClose: 5000,
          })
        } else if (task.status === TaskStatus.FAILED) {
          notifiedTasksRef.current.add(task.id)
          activeTasksRef.current.delete(task.id)

          notifications.show({
            title: t('tasks.failed'),
            message: task.error_message || `${task.task_name} ${t('tasks.failedMessage')}`,
            color: 'red',
            autoClose: 8000,
          })
        } else if (task.status === TaskStatus.CANCELLED) {
          // Also handle cancelled tasks
          notifiedTasksRef.current.add(task.id)
          activeTasksRef.current.delete(task.id)
        }
      }

      // Update last check timestamp for next iteration
      lastCheckRef.current = now
    } catch (error) {
      // Silently fail - we don't want to spam errors for background polling
      console.debug('Task notification polling error:', error)
    }
  }, [t])

  useEffect(() => {
    // Initial check to capture active tasks
    checkTasks()

    // Poll every 5 seconds
    intervalRef.current = setInterval(checkTasks, 5000)

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [checkTasks])
}

export default useTaskNotifications
