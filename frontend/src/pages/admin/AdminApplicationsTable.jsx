import { useState } from 'react'
import { Button } from '@alfalab/core-components-button'
import { Input } from '@alfalab/core-components-input'
import { Select } from '@alfalab/core-components-select'

const statusLabels = {
  PRESCORING: 'Прескоринг',
  SCORING: 'Скоринг',
  INFO: 'Нужны данные',
  SUCCESS: 'Одобрено',
  AWAITING_DISBURSEMENT: 'Ожидает выдачи',
  COMPLETED: 'Исполнена',
  REJECTED: 'Отклонено',
}

const statusOptions = [
  { key: 'all', content: 'Все статусы' },
  ...Object.entries(statusLabels).map(([key, content]) => ({ key, content })),
]

const formatMoney = (value) =>
  `${new Intl.NumberFormat('ru-RU').format(value)} ₽`

const formatDate = (value) =>
  new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))

function AdminApplicationsTable({ applications, onOpen }) {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [dateDraft, setDateDraft] = useState({ from: '', to: '' })
  const [dateFilter, setDateFilter] = useState({ from: '', to: '' })

  // Имитирует набор, который позднее будет возвращать бэкенд с dateFrom/dateTo.
  const backendFilteredApplications = applications.filter((application) => {
    const createdDate = application.createdAt.slice(0, 10)
    return (
      (!dateFilter.from || createdDate >= dateFilter.from) &&
      (!dateFilter.to || createdDate <= dateFilter.to)
    )
  })

  const normalizedSearch = search.trim().toLowerCase()
  const visibleApplications = backendFilteredApplications.filter((application) => {
    const matchesStatus = status === 'all' || application.status === status
    const matchesSearch =
      !normalizedSearch ||
      application.id.toLowerCase().includes(normalizedSearch) ||
      application.clientName.toLowerCase().includes(normalizedSearch) ||
      application.phoneNumber.includes(normalizedSearch) ||
      application.inn.includes(normalizedSearch)

    return matchesStatus && matchesSearch
  })

  const applyDateFilter = (event) => {
    event.preventDefault()
    setDateFilter(dateDraft)
  }

  const resetFilters = () => {
    setSearch('')
    setStatus('all')
    setDateDraft({ from: '', to: '' })
    setDateFilter({ from: '', to: '' })
  }

  return (
    <section className="admin-applications">
      <header className="admin-page-heading">
        <div>
          <span>Кредитный конвейер</span>
          <h1>Заявки</h1>
          <p>Все клиентские заявки и их текущие статусы.</p>
        </div>
        <div className="admin-page-heading__count">
          <strong>{visibleApplications.length}</strong>
          <span>найдено</span>
        </div>
      </header>

      <div className="admin-filters">
        <form className="admin-date-filter" onSubmit={applyDateFilter}>
          <label>
            <span>Дата от</span>
            <input
              type="date"
              value={dateDraft.from}
              max={dateDraft.to || undefined}
              onChange={(event) =>
                setDateDraft((current) => ({ ...current, from: event.target.value }))
              }
            />
          </label>
          <label>
            <span>Дата до</span>
            <input
              type="date"
              value={dateDraft.to}
              min={dateDraft.from || undefined}
              onChange={(event) =>
                setDateDraft((current) => ({ ...current, to: event.target.value }))
              }
            />
          </label>
          <Button type="submit" view="secondary" size={48}>
            Применить даты
          </Button>
        </form>

        <div className="admin-client-filters">
          <Input
            block
            size={48}
            label="Поиск по ID, клиенту, телефону или ИНН"
            value={search}
            onChange={(_, { value }) => setSearch(value)}
            clear="auto"
            onClear={() => setSearch('')}
          />
          <Select
            block
            size={48}
            label="Статус"
            options={statusOptions}
            selected={status}
            onChange={({ selected }) => setStatus(selected?.key || 'all')}
          />
          <Button type="button" view="transparent" size={48} onClick={resetFilters}>
            Сбросить
          </Button>
        </div>
      </div>

      <div className="admin-table-card">
        <div className="admin-table-scroll">
          <table className="admin-table">
            <thead>
              <tr>
                <th>ID заявки</th>
                <th>Клиент</th>
                <th>Цель и сумма</th>
                <th>Статус</th>
                <th>Создана</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {visibleApplications.map((application) => (
                <tr key={application.id} onClick={() => onOpen(application.id)}>
                  <td>
                    <code>{application.id.slice(0, 8)}</code>
                  </td>
                  <td>
                    <strong>{application.clientName}</strong>
                    <small>{application.inn}</small>
                  </td>
                  <td>
                    <strong>{application.purpose}</strong>
                    <small>{formatMoney(application.creditSum)}</small>
                  </td>
                  <td>
                    <span className={`admin-status admin-status_${application.status.toLowerCase()}`}>
                      {statusLabels[application.status] || application.status}
                    </span>
                  </td>
                  <td>{formatDate(application.createdAt)}</td>
                  <td>
                    <Button type="button" view="text" size={40}>
                      Открыть
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {visibleApplications.length === 0 && (
          <div className="admin-table-empty">
            <strong>Заявки не найдены</strong>
            <p>Измените параметры поиска или сбросьте фильтры.</p>
          </div>
        )}
      </div>
    </section>
  )
}

export default AdminApplicationsTable
