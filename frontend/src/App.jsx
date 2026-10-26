import { useEffect, useState } from 'react'
import { api, ApiError } from './api'
import AdminPage from './pages/AdminPage'
import CabinetPage from './pages/CabinetPage'
import RegistrationPage from './pages/RegistrationPage'

function App() {
  const [sessionLoading, setSessionLoading] = useState(true)
  const [authMode, setAuthMode] = useState('registration')
  const [userData, setUserData] = useState(null)
  const [applications, setApplications] = useState([])
  const [initialApplicationId, setInitialApplicationId] = useState(null)

  const loadClientApplications = async () => {
    const response = await api.getApplications()
    setApplications(response.items)
  }

  useEffect(() => {
    const restoreSession = async () => {
      try {
        const user = await api.getMe()
        setUserData(user)

        if (!user.isAdmin) {
          await loadClientApplications()
        }
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 401) {
          console.error(error)
        }
      } finally {
        setSessionLoading(false)
      }
    }

    restoreSession()
  }, [])

  const handleAuthenticated = async (form, mode) => {
    let applicationId = null

    if (mode === 'login') {
      await api.login(form.phoneNumber)
    } else {
      const response = await api.register({
        phoneNumber: form.phoneNumber,
        inn: form.inn,
        creditSum: form.creditSum / 100,
        purpose: form.purpose,
        termMonths: form.termMonths,
        bkiConsent: form.bkiConsent,
        revenueLast12m: form.revenue ? form.revenue / 100 : null,
        refinanceLoanIds: [],
        companyName: null,
        hasCollateral: form.hasCollateral,
      })
      applicationId = response.applicationId
    }

    const user = await api.getMe()
    if (!user.isAdmin) {
      await loadClientApplications()
    }
    setInitialApplicationId(applicationId)
    setUserData(user)
  }

  const handleAddApplication = async (data) => {
    const application = await api.createApplication({
      creditSum: data.creditSum / 100,
      purpose: data.purpose,
      termMonths: data.termMonths,
      hasCollateral: data.hasCollateral,
      revenueLast12m: data.revenue ? data.revenue / 100 : null,
    })
    setApplications((current) => [...current, application])
    return application
  }

  const handleApplicationUpdated = (application) => {
    setApplications((current) =>
      current.map((item) =>
        item.id === application.id ? { ...item, ...application } : item,
      ),
    )
  }

  const handleLogout = async () => {
    try {
      await api.logout()
    } finally {
      setUserData(null)
      setApplications([])
      setInitialApplicationId(null)
      setAuthMode('login')
    }
  }

  if (sessionLoading) {
    return <main className="app-loading">Загружаем личный кабинет…</main>
  }

  if (userData?.isAdmin) {
    return <AdminPage onLogout={handleLogout} />
  }

  if (userData) {
    return (
      <CabinetPage
        userData={userData}
        applications={applications}
        initialApplicationId={initialApplicationId}
        onAddApplication={handleAddApplication}
        onApplicationUpdated={handleApplicationUpdated}
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
