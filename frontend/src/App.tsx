import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { MantineProvider } from '@mantine/core'
import { Notifications } from '@mantine/notifications'
import { ModalsProvider } from '@mantine/modals'
import ProtectedRoute from './components/ProtectedRoute'
import AppLayout from './components/AppLayout'
import Login from './pages/Login'
import AuthCallback from './pages/AuthCallback'
import Dashboard from './pages/Dashboard'
import ImportExport from './pages/ImportExport'
import Import from './pages/Import'
import Export from './pages/Export'
import Agencies from './pages/Agencies'
import RoutesPage from './pages/Routes'
import Stops from './pages/Stops'
import Trips from './pages/Trips'
import MapPage from './pages/Map'
import Feeds from './pages/Feeds'
import Calendars from './pages/Calendars'
import FareAttributes from './pages/FareAttributes'
import FareRules from './pages/FareRules'
import StopTimes from './pages/StopTimes'
import TaskManager from './pages/TaskManager'
import AuditLogs from './pages/AuditLogs'
import AgencyMerge from './pages/AgencyMerge'
import AgencyMergeWizard from './pages/AgencyMergeWizard'
import AgencySplit from './pages/AgencySplit'
import ValidationSettings from './pages/ValidationSettings'
import Teams from './pages/Teams'
import Realtime from './pages/Realtime'
import Settings from './pages/Settings'
import JoinTeam from './pages/JoinTeam'
import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'

function App() {
  return (
    <MantineProvider defaultColorScheme="auto">
      <ModalsProvider>
        <Notifications position="top-right" zIndex={100002} />
        <BrowserRouter>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<Login />} />
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/join" element={<JoinTeam />} />

            {/* Protected routes */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <Dashboard />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/agencies"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <Agencies />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/feeds/import"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <Import />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/feeds/export"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <Export />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            {/* Backwards compatibility redirect */}
            <Route path="/import-export" element={<Navigate to="/feeds/import" replace />} />

            <Route
              path="/routes"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <RoutesPage />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/stops"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <Stops />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/trips"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <Trips />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/map"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <MapPage />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route path="/map-editor" element={<Navigate to="/map" replace />} />

            <Route
              path="/feeds"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <Feeds />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/calendars"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <Calendars />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/fare-attributes"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <FareAttributes />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/fare-rules"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <FareRules />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/stop-times"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <StopTimes />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/tasks"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <TaskManager />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/audit"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <AuditLogs />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/agencies/merge"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <AgencyMergeWizard />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/agencies/merge/simple"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <AgencyMerge />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/agencies/split"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <AgencySplit />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/validation-settings"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <ValidationSettings />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/teams"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <Teams />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/realtime"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <Realtime />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            <Route
              path="/settings"
              element={
                <ProtectedRoute>
                  <AppLayout>
                    <Settings />
                  </AppLayout>
                </ProtectedRoute>
              }
            />

            {/* Catch all - redirect to home */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ModalsProvider>
    </MantineProvider>
  )
}

export default App
