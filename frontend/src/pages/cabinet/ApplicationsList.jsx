import { useEffect, useState } from 'react'
import { AmountInput } from '@alfalab/core-components-amount-input'
import { Button } from '@alfalab/core-components-button'
import { Modal } from '@alfalab/core-components-modal'
import { Select } from '@alfalab/core-components-select'
import { creditPurposeOptions, getCreditPurposeLabel } from '../../data/creditPurposes'
import './ApplicationsList.css'

const statusLabels = {
  INFO: 'Нужны данные',
  PRESCORING: 'Прескоринг',
  SCORING: 'Скоринг',
  SUCCESS: 'Одобрено',
  OFFER: 'Есть предложение',
  AWAITING_DISBURSEMENT: 'Ожидает выдачи',
  COMPLETED: 'Исполнена',
  REJECTED: 'Отклонено',
}

const initialApplication = {
  creditSum: null,
  purpose: '',
  termMonths: 24,
}

const termOptions = [6, 12, 18, 24, 30, 36].map((months) => ({
  key: String(months),
  content: `${months} месяцев`,
}))

const formatAmount = (value) => {
  if (!value) return 'Сумма не указана'
  return `${new Intl.NumberFormat('ru-RU').format(value)} ₽`
}

function ApplicationsList({ applications, onOpen, onAdd, openCreate, onCreateOpened }) {
  const [modalOpen, setModalOpen] = useState(false)
  const [form, setForm] = useState(initialApplication)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const formComplete = Boolean(form.creditSum && form.purpose && form.termMonths)

  useEffect(() => {
    if (openCreate) {
      setModalOpen(true)
      onCreateOpened()
    }
  }, [openCreate, onCreateOpened])

  const setField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const closeModal = () => {
    setModalOpen(false)
    setForm(initialApplication)
    setError('')
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')

    try {
      const application = await onAdd(form)
      closeModal()
      onOpen(application.id, application)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <section className="applications-page">
        <header className="applications-page__header">
          <div>
            <span className="applications-page__eyebrow">Кредитный конвейер</span>
            <h1>Мои заявки</h1>
            <p>Следите за решениями и создавайте новые заявки на кредит.</p>
          </div>
          <Button
            type="button"
            view="accent"
            size={48}
            onClick={() => setModalOpen(true)}
          >
            Новая заявка
          </Button>
        </header>

        <div className="applications-grid">
          {applications.map((application) => (
            <article className="application-card" key={application.id}>
              <div className="application-card__top">
                <span className="application-card__number">
                  Заявка №{application.number}
                </span>
                <span
                  className={`application-card__status application-card__status_${application.status.toLowerCase()}`}
                >
                  {statusLabels[application.status] || application.status}
                </span>
              </div>

              <h2>{getCreditPurposeLabel(application.purpose)}</h2>
              <div className="application-card__amount">
                {formatAmount(application.creditSum)}
              </div>
              <div className="application-card__amount-label">сумма кредита</div>

              <Button
                type="button"
                view="secondary"
                size={48}
                block
                onClick={() => onOpen(application.id)}
              >
                Открыть заявку
              </Button>
            </article>
          ))}
        </div>
      </section>

      <Modal
        open={modalOpen}
        onClose={closeModal}
        size={500}
        hasCloser
        scrollLock
      >
        <Modal.Header
          title="Новая заявка"
          subtitle="Укажите желаемые условия кредита"
        />
        <Modal.Content>
          <form
            id="new-application-form"
            className="new-application-form"
            onSubmit={handleSubmit}
          >
            <AmountInput
              block
              size={56}
              label={
                <>
                  Желаемая сумма кредита <span className="new-application-required">*</span>
                </>
              }
              value={form.creditSum}
              onChange={(_, { value }) => setField('creditSum', value)}
              currency="RUR"
              integersOnly
              required
            />
            <Select
              block
              size={56}
              label={
                <>
                  Цель кредита <span className="new-application-required">*</span>
                </>
              }
              placeholder="Выберите цель"
              options={creditPurposeOptions}
              selected={form.purpose || null}
              onChange={({ selected }) => setField('purpose', selected?.key ?? '')}
            />
            <Select
              block
              size={56}
              label={
                <>
                  Срок кредита <span className="new-application-required">*</span>
                </>
              }
              options={termOptions}
              selected={String(form.termMonths)}
              onChange={({ selected }) =>
                setField('termMonths', Number(selected?.key || 24))
              }
            />
            {error && <div className="new-application-error">{error}</div>}
          </form>
        </Modal.Content>
        <Modal.Footer layout="column">
          <Button
            type="submit"
            form="new-application-form"
            view="accent"
            size={56}
            block
            disabled={!formComplete || submitting}
          >
            {submitting ? 'Создаём…' : 'Создать заявку'}
          </Button>
        </Modal.Footer>
      </Modal>
    </>
  )
}

export default ApplicationsList
