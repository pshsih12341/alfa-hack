import { useEffect, useState } from 'react'
import { AmountInput } from '@alfalab/core-components-amount-input'
import { Button } from '@alfalab/core-components-button'
import { Input } from '@alfalab/core-components-input'
import { Modal } from '@alfalab/core-components-modal'
import { api } from '../api'
import Logo from '../components/Logo'
import { getCreditPurposeLabel } from '../data/creditPurposes'
import { CREDIT_SUM_MIN, formatMoney, formatMonths, formatRate, readFileAsBase64 } from '../format'
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

const PENDING_STATUSES = ['PRESCORING', 'SCORING']
const MIN_PRESCORING_DELAY = 5_000
const MAX_PRESCORING_DELAY = 10_000
const MAX_STATEMENT_FILES = 5
const MAX_STATEMENT_BYTES = 5 * 1024 * 1024

const calculateMonthlyPayment = (amount, annualRate, months) => {
  if (!amount || !months) return 0
  if (!annualRate) return Math.round(amount / months)

  const monthlyRate = annualRate / 100 / 12
  const factor = (1 + monthlyRate) ** months
  return Math.round((amount * monthlyRate * factor) / (factor - 1))
}

// Сроки, на которые ML одобрил хотя бы минимальную сумму (maxSum = null — срок недоступен).
const availableTerms = (maxByTerm) => (maxByTerm || []).filter((item) => item.maxSum)

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
  const [prescoringHold, setPrescoringHold] = useState(null)
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

  const openApplication = async (id, initialApplication, forcePrescoring = false) => {
    const currentApplication =
      initialApplication || applications.find((application) => application.id === id)

    setActiveApplicationId(id)
    setApplicationDetails(currentApplication)
    if (forcePrescoring || PENDING_STATUSES.includes(currentApplication?.status)) {
      const delay =
        MIN_PRESCORING_DELAY +
        Math.floor(Math.random() * (MAX_PRESCORING_DELAY - MIN_PRESCORING_DELAY + 1))
      setPrescoringHold({ applicationId: id, until: Date.now() + delay })
    } else {
      setPrescoringHold(null)
    }
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
      openApplication(initialApplicationId, initialApplication, true)
    }
  }, [])

  useEffect(() => {
    if (!prescoringHold) return undefined

    const timer = window.setTimeout(
      () => setPrescoringHold(null),
      Math.max(0, prescoringHold.until - Date.now()),
    )
    return () => window.clearTimeout(timer)
  }, [prescoringHold])

  useEffect(() => {
    const status = applicationDetails?.status
    if (
      view !== 'application' ||
      !activeApplicationId ||
      !PENDING_STATUSES.includes(status)
    ) {
      return undefined
    }

    // Первые 30 секунд опрашиваем часто, дальше реже, но не перестаём:
    // если ML был недоступен, решение придёт после повторного скоринга.
    const slowAfter = Date.now() + 30_000
    let timer

    const poll = async () => {
      try {
        const details = await api.getApplication(activeApplicationId)
        updateApplication(details)
        if (!PENDING_STATUSES.includes(details.status)) return
      } catch (error) {
        setDetailsError(error.message)
      }
      const slow = Date.now() >= slowAfter
      if (slow) setPollingExpired(true)
      timer = window.setTimeout(poll, slow ? 5000 : 1500)
    }

    timer = window.setTimeout(poll, 1500)
    return () => window.clearTimeout(timer)
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

  const submitStatements = async (data) => {
    const response = await api.submitStatements(activeApplicationId, data)
    setPollingExpired(false)
    setDetailsError('')
    // Сразу показываем, что идёт анализ выписок, не дожидаясь следующего опроса.
    updateApplication({
      ...response,
      additionalInfo: {
        useAlfaAccount: Boolean(data.useAlfaAccount),
        statements: (data.statements || []).map(({ fileName }) => ({ fileName })),
      },
    })
  }

  const startNewApplication = () => {
    setCreateRequested(true)
    setView('applications')
  }

  const displayedApplication =
    prescoringHold?.applicationId === activeApplicationId
      ? { ...applicationDetails, status: 'PRESCORING' }
      : applicationDetails

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

        {view === 'application' && displayedApplication && (
          <section className="cabinet-content">
            <div className="application-detail-header">
              <button type="button" onClick={openApplications}>← Все заявки</button>
              <div className="application-detail-header__meta">
                <span>Заявка №{displayedApplication.number}</span>
                <strong>{getCreditPurposeLabel(displayedApplication.purpose)}</strong>
              </div>
              <span
                className={`application-detail-status application-detail-status_${displayedApplication.status.toLowerCase()}`}
              >
                {statusLabels[displayedApplication.status] || displayedApplication.status}
              </span>
            </div>

            {detailsLoading && <div className="details-message">Загружаем заявку…</div>}
            {detailsError && <div className="details-message details-message_error">{detailsError}</div>}
            {!detailsLoading && (
              <ApplicationStatus
                application={displayedApplication}
                pollingExpired={pollingExpired}
                onAccept={acceptApplication}
                onAcceptOffer={acceptOffer}
                onSubmitStatements={submitStatements}
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
  onSubmitStatements,
  onNewApplication,
}) {
  if (application.status === 'INFO') {
    return (
      <>
        <MessageStatus
          tone="info"
          caption="Проверка приостановлена"
          title="Нужны обороты по счетам"
          message={application.clientMessage || 'Для продолжения рассмотрения нужны дополнительные сведения.'}
        />
        <StatementsForm documents={application.documentsRequired} onSubmit={onSubmitStatements} />
      </>
    )
  }

  if (application.status === 'SUCCESS') {
    return <ApprovedStatus application={application} onAccept={onAccept} />
  }

  if (application.status === 'OFFER') {
    return (
      <>
        <OfferStatus application={application} onAccept={onAcceptOffer} />
        {application.documentsRequired?.length > 0 && (
          <ReconsiderPanel documents={application.documentsRequired} onSubmit={onSubmitStatements} />
        )}
      </>
    )
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

  const info = application.additionalInfo
  const stage2 = Boolean(info?.useAlfaAccount || info?.statements?.length)
  return <PrescoringStatus expired={pollingExpired} stage2={stage2} />
}

function ApprovedStatus({ application, onAccept }) {
  const product = application.products?.[0]
  const approved = application.approved

  // Решение ML: одобренные условия и максимум по каждому сроку.
  if (approved && availableTerms(application.maxByTerm).length) {
    return (
      <DecisionCalculator
        application={application}
        title={product?.product || 'Кредит одобрен'}
        message={`Одобрено ${formatMoney(approved.creditSum)} на ${formatMonths(approved.termMonths)} под ${formatRate(approved.rate)}. Можно взять меньше или выбрать другой срок.`}
        initialAmount={approved.creditSum}
        initialTerm={approved.termMonths}
        knownOptions={[approved]}
        onAccept={(amount, term, bankDetails) => onAccept({ amount, termMonths: term, ...bankDetails })}
      />
    )
  }

  if (!product) {
    return (
      <div className="details-message details-message_error">
        Не удалось загрузить условия одобрения. Обновите страницу.
      </div>
    )
  }
  return <ProductCalculator application={application} product={product} onAccept={onAccept} />
}

// Без ответа ML (mock-скоринг): лимиты продукта.
function ProductCalculator({ application, product, onAccept }) {
  const termLimit = product.termLimit
  const terms = []
  for (let months = termLimit.min; months <= termLimit.max; months += termLimit.step) terms.push(months)
  const requestedAmount = application.creditSum || product.limit.min
  const [amount, setAmount] = useState(
    Math.min(product.limit.max, Math.max(product.limit.min, requestedAmount)),
  )
  const [term, setTerm] = useState(
    terms.includes(application.termMonths) ? application.termMonths : terms[terms.length - 1],
  )
  const rate = application.rate ?? product.rate

  return (
    <CreditCalculator
      title={product.product}
      message={`Вам доступно до ${formatMoney(product.limit.max)}. Выберите нужную сумму и срок кредита.`}
      amount={amount}
      setAmount={setAmount}
      amountLimit={product.limit}
      terms={terms}
      term={term}
      setTerm={setTerm}
      rate={rate}
      onAccept={(bankDetails) => onAccept({ amount, termMonths: term, ...bankDetails })}
    />
  )
}

function OfferStatus({ application, onAccept }) {
  const offers = application.offers || []
  const firstOffer = offers[0]
  const terms = availableTerms(application.maxByTerm)
  const initialTerm = firstOffer?.termMonths ?? terms[terms.length - 1]?.termMonths
  const initialAmount = firstOffer?.creditSum ?? terms[terms.length - 1]?.maxSum

  if (!terms.length) {
    return <div className="details-message details-message_error">Не удалось загрузить варианты. Обновите страницу.</div>
  }

  return (
    <DecisionCalculator
      application={application}
      title="Выберите подходящие условия"
      message={application.clientMessage}
      initialAmount={initialAmount}
      initialTerm={initialTerm}
      knownOptions={offers}
      renderOffers={(amount, term, choose) => (
        <div className="ready-offers">
          {offers.map((offer) => {
            const selected = offer.creditSum === amount && offer.termMonths === term

            return (
              <button
                className={selected ? 'ready-offer ready-offer_selected' : 'ready-offer'}
                key={`${offer.creditSum}-${offer.termMonths}`}
                type="button"
                onClick={() => choose(offer)}
              >
                <div className="ready-offer__top">
                  <span>Готовый вариант</span>
                  <b>{selected ? '✓ Выбрано' : 'Выбрать'}</b>
                </div>
                {offer.product && (
                  <span className="ready-offer__product">{offer.product}</span>
                )}
                <strong>{formatMoney(offer.creditSum)}</strong>
                <small>
                  {formatMonths(offer.termMonths)} · {formatRate(offer.rate)} · {formatMoney(offer.monthlyPayment)} в месяц
                </small>
              </button>
            )
          })}
        </div>
      )}
      onAccept={(amount, term, bankDetails) => onAccept({ creditSum: amount, termMonths: term, ...bankDetails })}
    />
  )
}

// Подбор суммы и срока в пределах решения ML: на каждом сроке — не больше maxByTerm[срок].maxSum,
// недоступные сроки пропускаются. Ставка — готового варианта, если выбран он, иначе — срока.
function DecisionCalculator({
  application,
  title,
  message,
  initialAmount,
  initialTerm,
  knownOptions,
  renderOffers,
  onAccept,
}) {
  const items = availableTerms(application.maxByTerm)
  const terms = items.map((item) => item.termMonths)
  const limitMin = application.limit?.min ?? CREDIT_SUM_MIN
  const step = application.limit?.step || 50_000
  const startTerm = terms.includes(initialTerm) ? initialTerm : terms[terms.length - 1]
  const startItem = items.find((item) => item.termMonths === startTerm)
  const [term, setTerm] = useState(startTerm)
  const [amount, setAmount] = useState(Math.min(initialAmount || startItem.maxSum, startItem.maxSum))
  const item = items.find((candidate) => candidate.termMonths === term)
  const known = knownOptions.find((option) => option.creditSum === amount && option.termMonths === term)
  const rate = known?.rate ?? item.rate

  const changeTerm = (nextTerm) => {
    const next = items.find((candidate) => candidate.termMonths === nextTerm)
    setTerm(nextTerm)
    setAmount((current) => Math.max(limitMin, Math.min(current, next.maxSum)))
  }

  const choose = (option) => {
    setTerm(option.termMonths)
    setAmount(option.creditSum)
  }

  return (
    <CreditCalculator
      title={title}
      message={message}
      amount={amount}
      setAmount={setAmount}
      amountLimit={{ min: limitMin, max: item.maxSum, step }}
      terms={terms}
      term={term}
      setTerm={changeTerm}
      rate={rate}
      offers={renderOffers?.(amount, term, choose)}
      onAccept={(bankDetails) => onAccept(amount, term, bankDetails)}
    />
  )
}

function CreditCalculator({
  title,
  message,
  amount,
  setAmount,
  amountLimit,
  terms,
  term,
  setTerm,
  rate,
  offers,
  onAccept,
}) {
  const [modalOpen, setModalOpen] = useState(false)
  const monthlyPayment = calculateMonthlyPayment(amount, rate, term)
  const totalPayment = monthlyPayment * term
  const overpayment = Math.max(0, totalPayment - amount)
  const amountStep = amountLimit.step || 50_000
  const amountRange = amountLimit.max - amountLimit.min
  const amountProgress = amountRange > 0 ? ((amount - amountLimit.min) / amountRange) * 100 : 100
  const termIndex = Math.max(0, terms.indexOf(term))
  const termProgress = terms.length > 1 ? (termIndex / (terms.length - 1)) * 100 : 100

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
                disabled={amountRange <= 0}
                style={{ '--range-progress': `${amountProgress}%` }}
                onChange={(event) => setAmount(Math.min(amountLimit.max, Number(event.target.value)))}
              />
              <div className="calculator-range-labels">
                <span>{formatMoney(amountLimit.min)}</span>
                <span>{formatMoney(amountLimit.max)}</span>
              </div>
            </div>

            <div className="calculator-field">
              <div className="calculator-field__heading">
                <span>Срок кредита</span>
                <strong>{formatMonths(term)}</strong>
              </div>
              <input
                className="calculator-range"
                type="range"
                min={0}
                max={Math.max(0, terms.length - 1)}
                step={1}
                value={termIndex}
                disabled={terms.length < 2}
                style={{ '--range-progress': `${termProgress}%` }}
                onChange={(event) => setTerm(terms[Number(event.target.value)])}
              />
              <div className="calculator-range-labels">
                <span>{formatMonths(terms[0])}</span>
                <span>{formatMonths(terms[terms.length - 1])}</span>
              </div>
            </div>
          </div>

          <aside className="credit-calculator__result">
            <span>Платёж в месяц</span>
            <strong>{formatMoney(monthlyPayment)}</strong>
            <dl>
              <div><dt>Сумма</dt><dd>{formatMoney(amount)}</dd></div>
              <div><dt>Срок</dt><dd>{formatMonths(term)}</dd></div>
              <div><dt>Ставка</dt><dd>{formatRate(rate)}</dd></div>
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

// Этап 2: обороты по счёту в Альфе (alfaAccountConsent) или выписки других банков файлами 1С (bankStatements).
function StatementsForm({ documents, onSubmit }) {
  const useAlfaAccount = documents?.includes('alfaAccountConsent')
  const [files, setFiles] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const addFiles = (event) => {
    const picked = [...event.target.files]
    event.target.value = ''
    const tooBig = picked.find((file) => file.size > MAX_STATEMENT_BYTES)
    if (tooBig) {
      setError(`Файл ${tooBig.name} больше 5 МБ`)
      return
    }
    const next = [...files, ...picked]
    if (next.length > MAX_STATEMENT_FILES) {
      setError(`Можно загрузить не больше ${MAX_STATEMENT_FILES} файлов`)
      return
    }
    setFiles(next)
    setError('')
  }

  const removeFile = (index) => setFiles((current) => current.filter((_, i) => i !== index))

  const submit = async (makeData) => {
    setSubmitting(true)
    setError('')
    try {
      await onSubmit(await makeData())
    } catch (requestError) {
      setError(requestError.message)
      setSubmitting(false)
    }
  }

  const sendFiles = () =>
    submit(async () => ({
      statements: await Promise.all(
        files.map(async (file) => ({ fileName: file.name, content: await readFileAsBase64(file) })),
      ),
    }))

  return (
    <section className="statements-card">
      {useAlfaAccount ? (
        <>
          <h2>Обороты по счёту в Альфа-Банке</h2>
          <p>
            Разрешите использовать данные вашего расчётного счёта в Альфа-Банке — загружать выписки
            не нужно, решение придёт через несколько секунд.
          </p>
          <Button
            type="button"
            view="accent"
            size={56}
            disabled={submitting}
            onClick={() => submit(async () => ({ useAlfaAccount: true }))}
          >
            {submitting ? 'Отправляем…' : 'Использовать данные моего счёта'}
          </Button>
        </>
      ) : (
        <>
          <h2>Выписки по расчётным счетам</h2>
          <p>
            Загрузите выгрузки из 1С или банк-клиента в формате 1CClientBankExchange (.txt) за последние
            12 месяцев по всем счетам компании: до {MAX_STATEMENT_FILES} файлов, каждый до 5 МБ.
          </p>
          <label className="statements-upload">
            <input type="file" accept=".txt,text/plain" multiple onChange={addFiles} disabled={submitting} />
            <span>Выбрать файлы</span>
          </label>
          {files.length > 0 && (
            <ul className="statements-files">
              {files.map((file, index) => (
                <li key={`${file.name}-${index}`}>
                  <span>{file.name}</span>
                  <small>{Math.max(1, Math.round(file.size / 1024))} КБ</small>
                  <button type="button" onClick={() => removeFile(index)} disabled={submitting}>
                    Убрать
                  </button>
                </li>
              ))}
            </ul>
          )}
          <Button
            type="button"
            view="accent"
            size={56}
            disabled={!files.length || submitting}
            onClick={sendFiles}
          >
            {submitting ? 'Отправляем…' : 'Отправить выписки'}
          </Button>
        </>
      )}
      {error && <div className="details-message details-message_error">{error}</div>}
    </section>
  )
}

function ReconsiderPanel({ documents, onSubmit }) {
  const [open, setOpen] = useState(false)

  if (open) return <StatementsForm documents={documents} onSubmit={onSubmit} />

  return (
    <section className="statements-card statements-card_compact">
      <p>Нужна сумма больше? Покажите обороты по счетам — мы пересмотрим решение.</p>
      <Button type="button" view="secondary" size={48} onClick={() => setOpen(true)}>
        Пересмотреть по выпискам
      </Button>
    </section>
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
              <span>{formatRate(rate)} годовых · {formatMonths(term)}</span>
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

function PrescoringStatus({ expired, stage2 }) {
  const [secondsLeft, setSecondsLeft] = useState(10)

  useEffect(() => {
    const deadline = Date.now() + 10_000
    const timer = window.setInterval(() => {
      setSecondsLeft(Math.max(0, Math.ceil((deadline - Date.now()) / 1000)))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])

  return (
    <>
      <MessageStatus
        caption="Заявка принята"
        title={stage2 ? 'Анализируем обороты по счетам' : 'Сейчас идёт прескоринг'}
        message={
          stage2
            ? 'Считаем выручку и денежный поток по выпискам. Как только проверка завершится, здесь появится решение.'
            : 'Мы анализируем данные вашего бизнеса. Как только проверка завершится, здесь появится решение.'
        }
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
