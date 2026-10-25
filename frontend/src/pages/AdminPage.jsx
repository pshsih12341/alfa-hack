import { useEffect, useState } from 'react'
import { Button } from '@alfalab/core-components-button'
import { api } from '../api'
import Logo from '../components/Logo'
import AdminApplicationDetails from './admin/AdminApplicationDetails'
import AdminApplicationsTable from './admin/AdminApplicationsTable'
import './AdminPage.css'

function AdminPage({ onLogout }) {
  const [applications, setApplications] = useState([])
  const [selectedApplication, setSelectedApplication] = useState(null)
  const [listLoading, setListLoading] = useState(true)
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [error, setError] = useState('')

  const loadApplications = async (dateFilter = {}) => {
    setListLoading(true)
    setError('')

    try {
      const response = await api.getAdminApplications(dateFilter)
      setApplications(response.items)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setListLoading(false)
    }
  }

  useEffect(() => {
    loadApplications()
  }, [])

  const openApplication = async (id) => {
    setDetailsLoading(true)
    setError('')

    try {
      const application = await api.getAdminApplication(id)
      setSelectedApplication(application)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setDetailsLoading(false)
    }
  }

  const completeApplication = async (id) => {
    setError('')

    try {
      await api.completeAdminApplication(id)
      const application = await api.getAdminApplication(id)
      setSelectedApplication(application)
      setApplications((current) =>
        current.map((item) =>
          item.id === id
            ? { ...item, status: application.status, updatedAt: application.updatedAt }
            : item,
        ),
      )
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  return (
    <main className="admin">
      <header className="admin-header">
        <div className="admin-header__brand">
          <Logo />
          <span>Администратор</span>
        </div>
        <Button type="button" view="transparent" size={40} onClick={onLogout}>
          Выйти
        </Button>
      </header>

      <div className="admin-layout">
        {error && <div className="admin-message admin-message_error">{error}</div>}

        {detailsLoading ? (
          <div className="admin-message">Загружаем заявку…</div>
        ) : selectedApplication ? (
          <AdminApplicationDetails
            application={selectedApplication}
            onComplete={completeApplication}
            onBack={() => setSelectedApplication(null)}
          />
        ) : (
          <AdminApplicationsTable
            applications={applications}
            loading={listLoading}
            onDateFilter={loadApplications}
            onOpen={openApplication}
          />
        )}
      </div>
    </main>
  )
}

export default AdminPage
