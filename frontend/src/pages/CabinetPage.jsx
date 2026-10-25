import { useEffect, useState } from 'react'
import { AmountInput } from '@alfalab/core-components-amount-input'
import { Button } from '@alfalab/core-components-button'
import { Input } from '@alfalab/core-components-input'
import { Modal } from '@alfalab/core-components-modal'
import Logo from '../components/Logo'
import ApplicationsList from './cabinet/ApplicationsList'
import PersonalData from './cabinet/PersonalData'
import { approvedProductMock } from '../mocks/approvedProduct'
import './CabinetPage.css'

const statusLabels = {
  INFO: 'Нужны данные',
  PRESCORING: 'Прескоринг',
  SUCCESS: 'Одобрено',
  REJECTED: 'Отклонено',
}

const calculatorTerm = {
  min: 6,
  max: 60,
  step: 6,
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

function CabinetPage({ userData, applications, onAddApplication, onLogout }) {
  const [view, setView] = useState('applications')
  const [activeApplicationId, setActiveApplicationId] = useState(applications[0]?.id)
  const [scrollToAdditionalData, setScrollToAdditionalData] = useState(false)
  const activeApplication =
    applications.find(({ id }) => id === activeApplicationId) || applications[0]
  const profileApplication =
    applications.find(({ status }) => status === 'INFO') || activeApplication

  const openApplications = () => {
    setScrollToAdditionalData(false)
    setView('applications')
  }

  const openProfile = () => {
    setScrollToAdditionalData(false)
    setView('profile')
  }

  const openRequestedData = () => {
    setScrollToAdditionalData(true)
    setView('profile')
  }

  const addApplication = (data) => {
    const application = onAddApplication(data)
    setActiveApplicationId(application.id)
    setScrollToAdditionalData(false)
    setView('application')
  }

  const openApplication = (id) => {
    setActiveApplicationId(id)
    setScrollToAdditionalData(false)
    setView('application')
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
          <Button
            type="button"
            view="transparent"
            size={40}
            onClick={onLogout}
          >
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
          />
        )}

        {view === 'application' && activeApplication && (
          <section className="cabinet-content">
            <div className="application-detail-header">
              <button type="button" onClick={openApplications}>
                ← Все заявки
              </button>
              <div className="application-detail-header__meta">
                <span>Заявка №{activeApplication.number}</span>
                <strong>{activeApplication.purpose}</strong>
              </div>
              <span
                className={`application-detail-status application-detail-status_${activeApplication.status.toLowerCase()}`}
              >
                {statusLabels[activeApplication.status] || activeApplication.status}
              </span>
            </div>

            <ApplicationStatus
              application={activeApplication}
              status={activeApplication?.status || 'PRESCORING'}
              onOpenProfile={openRequestedData}
            />
          </section>
        )}

        {view === 'profile' && (
          <section className="cabinet-content">
            <button
              className="profile-back-button"
              type="button"
              onClick={openApplications}
            >
              ← К заявкам
            </button>
            <PersonalData
              data={userData}
              status={profileApplication?.status || 'PRESCORING'}
              shouldScrollToAdditionalData={scrollToAdditionalData}
            />
          </section>
        )}
      </div>
    </main>
  )
}

function ApplicationStatus({ application, status, onOpenProfile }) {
  if (status === 'INFO') {
    return <InfoRequiredStatus onOpenProfile={onOpenProfile} />
  }

  if (status === 'SUCCESS') {
    return <ApprovedStatus application={application} />
  }

  if (status === 'REJECTED') {
    return <RejectedStatus />
  }

  return <PrescoringStatus />
}

function InfoRequiredStatus({ onOpenProfile }) {
  return (
    <article className="application-status-card">
      <div className="info-visual" aria-hidden="true">
        <span>i</span>
      </div>
      <div className="prescoring-copy info-copy">
        <div className="prescoring-copy__caption">Проверка приостановлена</div>
        <h1>Нам потребовались дополнительные данные</h1>
        <p>
          Заполните несколько полей о компании, чтобы мы могли продолжить
          рассмотрение заявки.
        </p>
        <Button
          className="info-copy__button"
          type="button"
          view="accent"
          size={56}
          onClick={onOpenProfile}
        >
          Заполнить данные
        </Button>
      </div>
    </article>
  )
}

function ApprovedStatus({ application }) {
  const product = approvedProductMock
  const requestedAmount = application?.creditSum
    ? application.creditSum / 100
    : product.limit.min
  const initialAmount = Math.min(
    product.limit.max,
    Math.max(product.limit.min, requestedAmount),
  )
  const [amount, setAmount] = useState(initialAmount)
  const [term, setTerm] = useState(36)
  const [offerModalOpen, setOfferModalOpen] = useState(false)
  const [detailsSent, setDetailsSent] = useState(false)
  const [details, setDetails] = useState({ bankName: '', bic: '', accountNumber: '' })
  const detailsComplete = Object.values(details).every(Boolean)
  const rateLabel =
    product.rate === null ? 'Индивидуальная ставка' : `${product.rate}% годовых`
  const amountValid = amount >= product.limit.min && amount <= product.limit.max
  const monthlyPayment = calculateMonthlyPayment(amount, product.rate, term)
  const totalPayment = monthlyPayment * term
  const overpayment = Math.max(0, totalPayment - amount)
  const amountProgress = amountValid
    ? ((amount - product.limit.min) / (product.limit.max - product.limit.min)) * 100
    : 0
  const termProgress =
    ((term - calculatorTerm.min) / (calculatorTerm.max - calculatorTerm.min)) * 100

  const openOffer = () => {
    setOfferModalOpen(true)
    setDetailsSent(false)
  }

  const closeOffer = () => {
    setOfferModalOpen(false)
    setDetails({ bankName: '', bic: '', accountNumber: '' })
  }

  const setDetail = (field, value) => {
    setDetails((current) => ({ ...current, [field]: value }))
  }

  const submitDetails = (event) => {
    event.preventDefault()
    setDetailsSent(true)
  }

  return (
    <>
      <section className="credit-calculator">
        <header className="credit-calculator__header">
          <div className="credit-calculator__approved">Заявка одобрена</div>
          <h1>{product.product}</h1>
          <p>
            Вам доступно до {formatMoney(product.limit.max)}. Выберите нужную
            сумму и удобный срок кредита.
          </p>
          <div className="credit-calculator__tags">
            <span>{rateLabel}</span>
            <span>{product.withCollateral ? 'С залогом' : 'Без залога'}</span>
          </div>
        </header>

        <div className="credit-calculator__body">
          <div className="credit-calculator__controls">
            <div className="calculator-field">
              <AmountInput
                block
                size={64}
                label="Сумма кредита"
                value={amount === null ? null : amount * 100}
                onChange={(_, { value }) =>
                  setAmount(value === null ? null : value / 100)
                }
                currency="RUR"
                integersOnly
                error={
                  amount !== null && !amountValid
                    ? `Введите сумму от ${formatMoney(product.limit.min)} до ${formatMoney(product.limit.max)}`
                    : false
                }
              />
              <input
                className="calculator-range"
                type="range"
                min={product.limit.min}
                max={product.limit.max}
                step={100_000}
                value={amountValid ? amount : product.limit.min}
                style={{ '--range-progress': `${amountProgress}%` }}
                onChange={(event) => setAmount(Number(event.target.value))}
              />
              <div className="calculator-range-labels">
                <span>{formatMoney(product.limit.min)}</span>
                <span>{formatMoney(product.limit.max)}</span>
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
                min={calculatorTerm.min}
                max={calculatorTerm.max}
                step={calculatorTerm.step}
                value={term}
                style={{ '--range-progress': `${termProgress}%` }}
                onChange={(event) => setTerm(Number(event.target.value))}
              />
              <div className="calculator-range-labels">
                <span>{calculatorTerm.min} месяцев</span>
                <span>{calculatorTerm.max} месяцев</span>
              </div>
            </div>
          </div>

          <aside className="credit-calculator__result">
            <span>Платёж в месяц</span>
            <strong>{amountValid ? formatMoney(monthlyPayment) : '—'}</strong>
            <dl>
              <div>
                <dt>Сумма</dt>
                <dd>{amountValid ? formatMoney(amount) : '—'}</dd>
              </div>
              <div>
                <dt>Срок</dt>
                <dd>{term} месяцев</dd>
              </div>
              <div>
                <dt>Ставка</dt>
                <dd>{product.rate === null ? 'Индивидуально' : `${product.rate}%`}</dd>
              </div>
              <div>
                <dt>Переплата</dt>
                <dd>{amountValid ? formatMoney(overpayment) : '—'}</dd>
              </div>
            </dl>
            <Button
              type="button"
              view="accent"
              size={56}
              block
              disabled={!amountValid}
              onClick={openOffer}
            >
              Продолжить оформление
            </Button>
            <small>Расчёт предварительный и не является офертой</small>
          </aside>
        </div>
      </section>

      <Modal
        open={offerModalOpen}
        onClose={closeOffer}
        size={600}
        hasCloser
        scrollLock
      >
        <Modal.Header
          title={detailsSent ? 'Реквизиты отправлены' : 'Куда зачислить деньги'}
          subtitle={
            detailsSent
              ? 'Мы сохранили выбранное предложение'
              : 'Укажите расчётный счёт для получения кредита'
          }
        />

        <Modal.Content>
          {detailsSent ? (
            <div className="offer-modal-success">
              <span>✓</span>
              <h2>Всё готово</h2>
              <p>
                Реквизиты приняты. Дальше здесь появится следующий шаг оформления.
              </p>
            </div>
          ) : (
            <form
              id="receiving-details-form"
              className="receiving-details-form"
              onSubmit={submitDetails}
            >
              <div className="offer-modal-summary">
                <span>{product.product}</span>
                <strong>{formatMoney(amount)}</strong>
                <small>
                  {rateLabel} · {term} месяцев · {formatMoney(monthlyPayment)} в месяц
                </small>
              </div>

              <Input
                block
                size={56}
                label="Название банка"
                value={details.bankName}
                onChange={(_, { value }) => setDetail('bankName', value)}
                required
              />
              <Input
                block
                size={56}
                label="БИК"
                value={details.bic}
                onChange={(_, { value }) =>
                  setDetail('bic', value.replace(/\D/g, '').slice(0, 9))
                }
                inputMode="numeric"
                maxLength={9}
                required
              />
              <Input
                block
                size={56}
                label="Номер расчётного счёта"
                value={details.accountNumber}
                onChange={(_, { value }) =>
                  setDetail('accountNumber', value.replace(/\D/g, '').slice(0, 20))
                }
                inputMode="numeric"
                maxLength={20}
                required
              />
            </form>
          )}
        </Modal.Content>

        <Modal.Footer layout="column">
          {detailsSent ? (
            <Button type="button" view="accent" size={56} block onClick={closeOffer}>
              Готово
            </Button>
          ) : (
            <Button
              type="submit"
              form="receiving-details-form"
              view="accent"
              size={56}
              block
              disabled={!detailsComplete}
            >
              Отправить реквизиты
            </Button>
          )}
        </Modal.Footer>
      </Modal>
    </>
  )
}

function PrescoringStatus() {
  const [secondsLeft, setSecondsLeft] = useState(120)

  useEffect(() => {
    const deadline = Date.now() + 120_000
    const timer = window.setInterval(() => {
      setSecondsLeft(Math.max(0, Math.ceil((deadline - Date.now()) / 1000)))
    }, 1000)

    return () => window.clearInterval(timer)
  }, [])

  const minutes = String(Math.floor(secondsLeft / 60)).padStart(2, '0')
  const seconds = String(secondsLeft % 60).padStart(2, '0')

  return (
    <>
      <article className="application-status-card">
        <div className="prescoring-visual" aria-hidden="true">
          <div className="prescoring-visual__ring">
            <span />
          </div>
        </div>
        <div className="prescoring-copy">
          <div className="prescoring-copy__caption">Заявка принята</div>
          <h1>Сейчас идёт прескоринг</h1>
          <p>
            Мы анализируем данные вашего бизнеса. Как только проверка
            завершится, здесь появятся лучшие кредитные предложения.
          </p>
          <div className="prescoring-timer">
            {secondsLeft > 0 ? (
              <>
                <span>Осталось примерно</span>
                <strong>{minutes}:{seconds}</strong>
              </>
            ) : (
              <>
                <span>Завершаем проверку</span>
                <strong>Ещё немного</strong>
              </>
            )}
          </div>
        </div>
      </article>

      <div className="status-note">
        <span className="status-note__icon">i</span>
        <p>
          Обычно проверка занимает до двух минут. Иногда нам может понадобиться
          немного больше времени.
        </p>
      </div>
    </>
  )
}

function RejectedStatus() {
  return (
    <>
      <article className="application-status-card">
        <div className="rejected-visual" aria-hidden="true">
          <span />
        </div>
        <div className="prescoring-copy rejected-copy">
          <div className="prescoring-copy__caption">Решение по заявке</div>
          <h1>Сейчас мы не можем одобрить кредит</h1>
          <p>
            К сожалению, заявка не прошла проверку. Вы сможете подать новую
            заявку позже — возможно, к этому времени условия изменятся.
          </p>
        </div>
      </article>

      <div className="status-note">
        <span className="status-note__icon">i</span>
        <p>Это решение относится только к текущей заявке.</p>
      </div>
    </>
  )
}

export default CabinetPage
