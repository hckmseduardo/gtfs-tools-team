import { defineStore } from 'pinia'
import { ref } from 'vue'

interface EventType {
  id: string
  name: string
}

interface CalendarFilters {
  view: string
  eventType: string
  startDate: string
  endDate: string
}

export const useCalendarStore = defineStore('calendar', () => {
  const eventTypes = ref<EventType[]>([])
  const isLoading = ref(false)
  
  const filters = ref<CalendarFilters>({
    view: 'month',
    eventType: '',
    startDate: '',
    endDate: ''
  })

  const fetchEventTypes = async () => {
    // Prevent redundant fetches
    if (eventTypes.value.length > 0) return
    
    isLoading.value = true
    try {
      // Load event types - ensures filter has data to work with
      const response = await fetch('/api/calendar/event-types')
      if (response.ok) {
        eventTypes.value = await response.json()
      }
    } catch (error) {
      console.error('Failed to fetch event types:', error)
      // Provide fallback so filter remains usable
      eventTypes.value = []
    } finally {
      isLoading.value = false
    }
  }

  const setView = (view: string) => {
    filters.value.view = view
  }

  const setEventTypeFilter = (eventType: string) => {
    filters.value.eventType = eventType
  }

  const setDateRange = (start: string, end: string) => {
    filters.value.startDate = start
    filters.value.endDate = end
  }

  const resetFilters = () => {
    filters.value = {
      view: 'month',
      eventType: '',
      startDate: '',
      endDate: ''
    }
  }

  return {
    eventTypes,
    isLoading,
    filters,
    fetchEventTypes,
    setView,
    setEventTypeFilter,
    setDateRange,
    resetFilters
  }
})