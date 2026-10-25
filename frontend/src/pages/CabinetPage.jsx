import { useEffect, useState } from 'react'
import { AmountInput } from '@alfalab/core-components-amount-input'
import { Button } from '@alfalab/core-components-button'
import { Input } from '@alfalab/core-components-input'
import { Modal } from '@alfalab/core-components-modal'
import { api } from '../api'
import Logo from '../components/Logo'
import { getCreditPurposeLabel } from '../data/creditPurposes'
import ApplicationsList from './cabinet/ApplicationsList'
import PersonalData from './cabinet/PersonalData'
import './CabinetPage.css'

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

const formatMoney = (value) =>
  `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value)} ₽`

const calculateMonthlyPayment = (amount, annualRate, months) => {
  if (!amount || !months) return 0
  if (!annualRate) return Math.round(amount / months)

  const monthlyRate = annualRate / 100 / 12
  const factor = (1 + monthlyRate) ** months
  return Math.round((amount * monthlyRate * factor) / (factor - 1))
}

function CabinetPage({
  userData,
  applications,
  initialApplicationId,
  onAddApplication,
  onApplicationUpdated,
  onLogout,
}) {
  const initialApplication = applications.find(
    (application) => application.id === initialApplicationId,
  )
  const [view, setView] = useState(
    initialApplicationId ? 'application' : 'applications',
  )
  const [activeApplicationId, setActiveApplicationId] = useState(
    initialApplicationId,
  )
  const [applicationDetails, setApplicationDetails] = useState(
    initialApplication || null,
  )
  const [detailsLoading, setDetailsLoading] = useState(Boolean(initialApplicationId))
  const [detailsError, setDetailsError] = useState('')
  const [pollingExpired, setPollingExpired] = useState(false)
  const [createRequested, setCreateRequested] = useState(false)

  const updateApplication = (application) => {
    setApplicationDetails((current) => ({ ...current, ...application }))
    onApplicationUpdated(application)
  }

  const openApplications = () => {
    setView('applications')
    setDetailsError('')
  }

  const openProfile = () => setView('profile')

  const addApplication = async (data) => {
    return onAddApplication(data)
  }

  const openApplication = async (id, initialApplication) => {
    setActiveApplicationId(id)
    setApplicationDetails(
      initialApplication || applications.find((application) => application.id === id),
    )
    setDetailsError('')
    setPollingExpired(false)
    setView('application')
    setDetailsLoading(true)

    try {
      const details = await api.getApplication(id)
      updateApplication(details)
    } catch (error) {
      setDetailsError(error.message)
    } finally {
      setDetailsLoading(false)
    }
  }

  useEffect(() => {
    if (initialApplicationId) {
      openApplication(initialApplicationId, initialApplication)
    }
  }, [])

  useEffect(() => {
    const status = applicationDetails?.status
    if (
      view !== 'application' ||
      !activeApplicationId ||
      !['PRESCORING', 'SCORING'].includes(status)
    ) {
      return undefined
    }

    const deadline = Date.now() + 30_000
    let requestInProgress = false

    const poll = async () => {
      if (Date.now() >= deadline) {
        setPollingExpired(true)
        window.clearInterval(timer)
        return
      }

      if (requestInProgress) return
      requestInProgress = true

      try {
        const details = await api.getApplication(activeApplicationId)
        updateApplication(details)
        if (!['PRESCORING', 'SCORING'].includes(details.status)) {
          window.clearInterval(timer)
        }
      } catch (error) {
        setDetailsError(error.message)
      } finally {
        requestInProgress = false
      }
    }

    const timer = window.setInterval(poll, 1500)
    return () => window.clearInterval(timer)
  }, [activeApplicationId, applicationDetails?.status, view])

  const acceptApplication = async (data) => {
    const response = await api.acceptApplication(activeApplicationId, data)
    updateApplication(response)
    return response
  }

  const acceptOffer = async (data) => {
    const response = await api.acceptOffer(activeApplicationId, data)
    updateApplication(response)
    return response
  }

  const startNewApplication = () => {
    setCreateRequested(true)
    setView('applications')
  }

  return (
    <main className="cabinet">
      <header className="cabinet-header">
        <Logo />
        <div className="cabinet-header__navigation">
          <button
            className={view === 'profile' ? 'profile-button active' : 'profile-button'}
            type="button"
            onClick={openProfile}
          >
            <span className="profile-button__avatar">Л</span>
            <span className="profile-button__copy">
              <strong>Профиль</strong>
              <small>{userData.phoneNumber || 'Личные данные'}</small>
            </span>
          </button>
          <Button type="button" view="transparent" size={40} onClick={onLogout}>
            Выйти
          </Button>
        </div>
      </header>

      <div className="cabinet-layout">
        {view === 'applications' && (
          <ApplicationsList
            applications={applications}
            onOpen={openApplication}
            onAdd={addApplication}
            openCreate={createRequested}
            onCreateOpened={() => setCreateRequested(false)}
          />
        )}

        {view === 'application' && applicationDetails && (
          <section className="cabinet-content">
            <div className="application-detail-header">
              <button type="button" onClick={openApplications}>← Все заявки</button>
              <div className="application-detail-header__meta">
                <span>Заявка №{applicationDetails.number}</span>
                <strong>{getCreditPurposeLabel(applicationDetails.purpose)}</strong>
              </div>
              <span
                className={`application-detail-status application-detail-status_${applicationDetails.status.toLowerCase()}`}
              >
                {statusLabels[applicationDetails.status] || applicationDetails.status}
              </span>
            </div>

            {detailsLoading && <div className="details-message">Загружаем заявку…</div>}
            {detailsError && <div className="details-message details-message_error">{detailsError}</div>}
            {!detailsLoading && (
              <ApplicationStatus
                application={applicationDetails}
                pollingExpired={pollingExpired}
                onAccept={acceptApplication}
                onAcceptOffer={acceptOffer}
                onNewApplication={startNewApplication}
              />
            )}
          </section>
        )}

        {view === 'profile' && (
          <section className="cabinet-content">
            <button className="profile-back-button" type="button" onClick={openApplications}>
              ← К заявкам
            </button>
            <PersonalData data={userData} />
          </section>
        )}
      </div>
    </main>
  )
}

function ApplicationStatus({
  application,
  pollingExpired,
  onAccept,
  onAcceptOffer,
  onNewApplication,
}) {
  if (application.status === 'INFO') {
    return (
      <MessageStatus
        tone="info"
        caption="Проверка приостановлена"
        title="Нам потребовались дополнительные данные"
        message={application.clientMessage || 'Для продолжения рассмотрения нужны дополнительные сведения.'}
      />
    )
  }

  if (application.status === 'SUCCESS') {
    if (!application.products?.[0]) {
      return <div className="details-message details-message_error">Бэк не вернул одобренный продукт.</div>
    }
    return <ApprovedStatus application={application} onAccept={onAccept} />
  }

  if (application.status === 'OFFER') {
    return <OfferStatus application={application} onAccept={onAcceptOffer} />
  }

  if (application.status === 'REJECTED') {
    return (
      <RejectedStatus
        message={application.clientMessage}
        onNewApplication={onNewApplication}
      />
    )
  }

  if (application.status === 'AWAITING_DISBURSEMENT') {
    return (
      <MessageStatus
        caption="Условия приняты"
        title="Заявка ожидает выдачи"
        message="Реквизиты сохранены. Банк готовит выдачу денежных средств."
      />
    )
  }

  if (application.status === 'COMPLETED') {
    return (
      <MessageStatus
        caption="Кредит выдан"
        title="Заявка исполнена"
        message="Денежные средства перечислены по указанным реквизитам."
      />
    )
  }

  return <PrescoringStatus expired={pollingExpired} />
}

function ApprovedStatus({ application, onAccept }) {
  const product = application.products[0]
  const termLimit = product.termLimit
  const requestedAmount = application.creditSum || product.limit.min
  const initialAmount = Math.min(product.limit.max, Math.max(product.limit.min, requestedAmount))
  const initialTerm = Math.min(
    termLimit.max,
    Math.max(termLimit.min, application.termMonths || 24),
  )
  const [amount, setAmount] = useState(initialAmount)
  const [term, setTerm] = useState(initialTerm)
  const rate = application.rate ?? product.rate
  const monthlyPayment = calculateMonthlyPayment(amount, rate, term)
  const amountProgress = ((amount - product.limit.min) / (product.limit.max - product.limit.min)) * 100
  const termProgress = ((term - termLimit.min) / (termLimit.max - termLimit.min)) * 100

  return (
    <CreditCalculator
      title={product.product}
      message={`Вам доступно до ${formatMoney(product.limit.max)}. Выберите нужную сумму и срок кредита.`}
      amount={amount}
      setAmount={setAmount}
      amountLimit={product.limit}
      term={term}
      setTerm={setTerm}
      termLimit={termLimit}
      rate={rate}
      monthlyPayment={monthlyPayment}
      amountProgress={amountProgress}
      termProgress={termProgress}
      onAccept={(bankDetails) => onAccept({ amount, termMonths: term, ...bankDetails })}
    />
  )
}

function OfferStatus({ application, onAccept }) {
  const firstOffer = application.offers?.[0]
  const firstTerm = firstOffer?.termMonths || application.termLimit.min
  const firstTermData = application.maxByTerm.find((item) => item.termMonths === firstTerm)
  const [term, setTerm] = useState(firstTerm)
  const [amount, setAmount] = useState(firstOffer?.creditSum || firstTermData.maxSum)
  const termData = application.maxByTerm.find((item) => item.termMonths === term)
  const maxAmount = termData?.maxSum || application.limit.min
  const amountLimit = { ...application.limit, max: maxAmount }
  const rate = termData?.rate ?? firstOffer?.rate ?? application.rate
  const monthlyPayment = calculateMonthlyPayment(amount, rate, term)
  const amountProgress = maxAmount === application.limit.min
    ? 100
    : ((amount - application.limit.min) / (maxAmount - application.limit.min)) * 100
  const termProgress = ((term - application.termLimit.min) /
    (application.termLimit.max - application.termLimit.min)) * 100

  const changeTerm = (nextTerm) => {
    const next = application.maxByTerm.find((item) => item.termMonths === nextTerm)
    setTerm(nextTerm)
    setAmount((current) => Math.min(current, next.maxSum))
  }

  const chooseOffer = (offer) => {
    setAmount(offer.creditSum)
    setTerm(offer.termMonths)
  }

  return (
    <CreditCalculator
      title="Выберите подходящие условия"
      message={application.clientMessage}
      amount={amount}
      setAmount={setAmount}
      amountLimit={amountLimit}
      term={term}
      setTerm={changeTerm}
      termLimit={application.termLimit}
      rate={rate}
      monthlyPayment={monthlyPayment}
      amountProgress={amountProgress}
      termProgress={termProgress}
      offers={
      <div className="ready-offers">
        {application.offers?.map((offer) => {
          const selected = offer.creditSum === amount && offer.termMonths === term

          return (
            <button
              className={selected ? 'ready-offer ready-offer_selected' : 'ready-offer'}
              key={`${offer.creditSum}-${offer.termMonths}`}
              type="button"
              onClick={() => chooseOffer(offer)}
            >
              <div className="ready-offer__top">
                <span>Готовый вариант</span>
                <b>{selected ? '✓ Выбрано' : 'Выбрать'}</b>
              </div>
              <strong>{formatMoney(offer.creditSum)}</strong>
              <small>{offer.termMonths} мес. · {offer.rate}% · {formatMoney(offer.monthlyPayment)} в месяц</small>
            </button>
          )
        })}
      </div>
      }
      onAccept={(bankDetails) => onAccept({ creditSum: amount, termMonths: term, ...bankDetails })}
    />
  )
}

function CreditCalculator({
  title,
  message,
  amount,
  setAmount,
  amountLimit,
  term,
  setTerm,
  termLimit,
  rate,
  monthlyPayment,
  amountProgress,
  termProgress,
  offers,
  onAccept,
}) {
  const [modalOpen, setModalOpen] = useState(false)
  const totalPayment = monthlyPayment * term
  const overpayment = Math.max(0, totalPayment - amount)
  const amountStep = amountLimit.step || 100_000

  return (
    <>
      <section className="credit-calculator">
        <header className="credit-calculator__header">
          <div className="credit-calculator__approved">Предложение банка</div>
          <h1>{title}</h1>
          <p>{message}</p>
        </header>

        <div
          className={
            offers
              ? 'credit-calculator__body credit-calculator__body_offer'
              : 'credit-calculator__body'
          }
        >
          {offers}
          <div className="credit-calculator__controls">
            <div className="calculator-field">
              <AmountInput
                block
                size={48}
                label="Сумма кредита"
                value={amount * 100}
                onChange={(_, { value }) => {
                  if (value === null) return
                  const rubles = Math.round(value / 100 / amountStep) * amountStep
                  setAmount(Math.min(amountLimit.max, Math.max(amountLimit.min, rubles)))
                }}
                currency="RUR"
                integersOnly
              />
              <input
                className="calculator-range"
                type="range"
                min={amountLimit.min}
                max={amountLimit.max}
                step={amountStep}
                value={amount}
                style={{ '--range-progress': `${amountProgress}%` }}
                onChange={(event) => setAmount(Number(event.target.value))}
              />
              <div className="calculator-range-labels">
                <span>{formatMoney(amountLimit.min)}</span>
                <span>{formatMoney(amountLimit.max)}</span>
              </div>
            </div>

            <div className="calculator-field">
              <div className="calculator-field__heading">
                <span>Срок кредита</span>
                <strong>{term} месяцев</strong>
              </div>
              <input
                className="calculator-range"
                type="range"
                min={termLimit.min}
                max={termLimit.max}
                step={termLimit.step}
                value={term}
                style={{ '--range-progress': `${termProgress}%` }}
                onChange={(event) => setTerm(Number(event.target.value))}
              />
              <div className="calculator-range-labels">
                <span>{termLimit.min} месяцев</span>
                <span>{termLimit.max} месяцев</span>
              </div>
            </div>
          </div>

          <aside className="credit-calculator__result">
            <span>Платёж в месяц</span>
            <strong>{formatMoney(monthlyPayment)}</strong>
            <dl>
              <div><dt>Сумма</dt><dd>{formatMoney(amount)}</dd></div>
              <div><dt>Срок</dt><dd>{term} месяцев</dd></div>
              <div><dt>Ставка</dt><dd>{rate}%</dd></div>
              <div><dt>Переплата</dt><dd>{formatMoney(overpayment)}</dd></div>
            </dl>
            <Button type="button" view="accent" size={56} block onClick={() => setModalOpen(true)}>
              Продолжить оформление
            </Button>
          </aside>
        </div>
      </section>

      <BankDetailsModal
        open={modalOpen}
        amount={amount}
        term={term}
        rate={rate}
        monthlyPayment={monthlyPayment}
        onClose={() => setModalOpen(false)}
        onSubmit={onAccept}
      />
    </>
  )
}

function BankDetailsModal({ open, amount, term, rate, monthlyPayment, onClose, onSubmit }) {
  const [details, setDetails] = useState({ bankName: '', bic: '', accountNumber: '' })
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState('')
  const complete =
    details.bankName.trim() &&
    details.bic.length === 9 &&
    details.accountNumber.length === 20

  const setField = (field, value) => setDetails((current) => ({ ...current, [field]: value }))

  const close = () => {
    onClose()
    setDetails({ bankName: '', bic: '', accountNumber: '' })
    setSent(false)
    setError('')
  }

  const submit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await onSubmit(details)
      setSent(true)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal open={open} onClose={close} size={600} hasCloser scrollLock>
      <Modal.Header
        title={sent ? 'Реквизиты отправлены' : 'Куда зачислить деньги'}
        subtitle={sent ? 'Выбранные условия сохранены' : 'Укажите расчётный счёт для получения кредита'}
      />
      <Modal.Content>
        {sent ? (
          <div className="offer-modal-success"><span>✓</span><h2>Всё готово</h2><p>Заявка перешла в ожидание выдачи.</p></div>
        ) : (
          <form id="receiving-details-form" className="receiving-details-form" onSubmit={submit}>
            <div className="offer-modal-summary">
              <span>{rate}% годовых · {term} месяцев</span>
              <strong>{formatMoney(amount)}</strong>
              <small>{formatMoney(monthlyPayment)} в месяц</small>
            </div>
            <Input block size={56} label="Название банка" value={details.bankName} onChange={(_, { value }) => setField('bankName', value)} required />
            <Input
              block
              size={56}
              label="БИК"
              value={details.bic}
              onChange={(_, { value }) => setField('bic', value.replace(/\D/g, '').slice(0, 9))}
              inputMode="numeric"
              maxLength={9}
              error={details.bic && details.bic.length !== 9 ? 'БИК должен содержать 9 цифр' : false}
              required
            />
            <Input
              block
              size={56}
              label="Номер расчётного счёта"
              value={details.accountNumber}
              onChange={(_, { value }) => setField('accountNumber', value.replace(/\D/g, '').slice(0, 20))}
              inputMode="numeric"
              maxLength={20}
              error={
                details.accountNumber && details.accountNumber.length !== 20
                  ? `Введите 20 цифр — сейчас ${details.accountNumber.length}`
                  : false
              }
              required
            />
            {error && <div className="details-message details-message_error">{error}</div>}
          </form>
        )}
      </Modal.Content>
      <Modal.Footer layout="column">
        {sent ? (
          <Button type="button" view="accent" size={56} block onClick={close}>Готово</Button>
        ) : (
          <Button type="submit" form="receiving-details-form" view="accent" size={56} block disabled={!complete || submitting}>
            {submitting ? 'Отправляем…' : 'Принять условия'}
          </Button>
        )}
      </Modal.Footer>
    </Modal>
  )
}

function PrescoringStatus({ expired }) {
  const [secondsLeft, setSecondsLeft] = useState(30)

  useEffect(() => {
    const deadline = Date.now() + 30_000
    const timer = window.setInterval(() => {
      setSecondsLeft(Math.max(0, Math.ceil((deadline - Date.now()) / 1000)))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <>
      <MessageStatus
        caption="Заявка принята"
        title="Сейчас идёт прескоринг"
        message="Мы анализируем данные вашего бизнеса. Как только проверка завершится, здесь появится решение."
        timer={expired || secondsLeft === 0 ? 'Проверка занимает чуть больше времени' : `00:${String(secondsLeft).padStart(2, '0')}`}
      />
      <div className="status-note"><span className="status-note__icon">i</span><p>Статус обновится автоматически.</p></div>
    </>
  )
}

function MessageStatus({ caption, title, message, timer, tone = '' }) {
  return (
    <article className={`application-status-card ${tone ? `application-status-card_${tone}` : ''}`}>
      <div className={tone === 'info' ? 'info-visual' : 'prescoring-visual'}>
        {tone === 'info' ? <span>i</span> : <div className="prescoring-visual__ring"><span /></div>}
      </div>
      <div className="prescoring-copy">
        <div className="prescoring-copy__caption">{caption}</div>
        <h1>{title}</h1>
        <p>{message}</p>
        {timer && <div className="prescoring-timer"><span>Ожидаем решение</span><strong>{timer}</strong></div>}
      </div>
    </article>
  )
}

function RejectedStatus({ message, onNewApplication }) {
  return (
    <>
      <article className="application-status-card">
        <div className="rejected-visual"><span /></div>
        <div className="prescoring-copy rejected-copy">
          <div className="prescoring-copy__caption">Решение по заявке</div>
          <h1>Сейчас мы не можем одобрить кредит</h1>
          <p>{message || 'По текущей заявке принято отрицательное решение.'}</p>
          <Button className="info-copy__button" type="button" view="accent" size={56} onClick={onNewApplication}>
            Подать новую заявку
          </Button>
        </div>
      </article>
    </>
  )
}

export default CabinetPage
