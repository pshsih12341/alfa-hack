import { useState } from 'react'
import { Button } from '@alfalab/core-components-button'
import Logo from '../components/Logo'
import { adminApplicationsMock } from '../mocks/adminApplications'
import AdminApplicationDetails from './admin/AdminApplicationDetails'
import AdminApplicationsTable from './admin/AdminApplicationsTable'
import './AdminPage.css'

function AdminPage({ onLogout }) {
  const [applications, setApplications] = useState(adminApplicationsMock)
  const [selectedApplicationId, setSelectedApplicationId] = useState(null)
  const selectedApplication = applications.find(
    ({ id }) => id === selectedApplicationId,
  )

  const completeApplication = (id) => {
    setApplications((current) =>
      current.map((application) =>
        application.id === id
          ? {
              ...application,
              status: 'COMPLETED',
              updatedAt: new Date().toISOString(),
            }
          : application,
      ),
    )
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
        {selectedApplication ? (
          <AdminApplicationDetails
            application={selectedApplication}
            onComplete={completeApplication}
            onBack={() => setSelectedApplicationId(null)}
          />
        ) : (
          <AdminApplicationsTable
            applications={applications}
            onOpen={setSelectedApplicationId}
          />
        )}
      </div>
    </main>
  )
}

export default AdminPage
