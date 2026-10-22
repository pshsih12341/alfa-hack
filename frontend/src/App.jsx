import { useState } from 'react'
import CabinetPage from './pages/CabinetPage'
import RegistrationPage from './pages/RegistrationPage'

function App() {
  const [page, setPage] = useState('registration')
  const [authMode, setAuthMode] = useState('registration')
  const [userData, setUserData] = useState({})
  const [applications, setApplications] = useState([])

  const handleAuthenticated = (data) => {
    setUserData(data)
    setApplications([
      {
        id: `application-${Date.now()}`,
        number: 1,
        status: 'INFO',
        creditSum: data.creditSum || 500_000_000,
        purpose: data.purpose || 'Пополнение оборотных средств',
      },
    ])
    setPage('cabinet')
  }

  const handleAddApplication = (data) => {
    const application = {
      ...data,
      id: `application-${Date.now()}`,
      number: applications.length + 1,
      status: 'PRESCORING',
    }

    setApplications((current) => [...current, application])
    return application
  }

  const handleLogout = () => {
    setUserData({})
    setApplications([])
    setAuthMode('login')
    setPage('registration')
  }

  if (page === 'cabinet') {
    return (
      <CabinetPage
        userData={userData}
        applications={applications}
        onAddApplication={handleAddApplication}
        onLogout={handleLogout}
      />
    )
  }

  return (
    <RegistrationPage
      initialMode={authMode}
      onAuthenticated={handleAuthenticated}
    />
  )
}

export default App
