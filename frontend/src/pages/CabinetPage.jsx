import { useState } from 'react'
import { Button } from '@alfalab/core-components-button'
import { Input } from '@alfalab/core-components-input'
import { Modal } from '@alfalab/core-components-modal'
import Logo from '../components/Logo'
import ApplicationsList from './cabinet/ApplicationsList'
import PersonalData from './cabinet/PersonalData'
import './CabinetPage.css'

const statusLabels = {
  INFO: 'Нужны данные',
  PRESCORING: 'Прескоринг',
  SUCCESS: 'Одобрено',
  REJECTED: 'Отклонено',
}

const creditOffers = [
  {
    id: 1,
    title: 'Лучшее предложение',
    amount: '5 000 000 ₽',
    rate: '17,9%',
    term: '36 месяцев',
    payment: '178 450 ₽',
  },
  {
    id: 2,
    title: 'Низкий ежемесячный платёж',
    amount: '5 000 000 ₽',
    rate: '19,4%',
    term: '48 месяцев',
    payment: '149 780 ₽',
  },
  {
    id: 3,
    title: 'Быстрое погашение',
    amount: '5 000 000 ₽',
    rate: '20,1%',
    term: '24 месяца',
    payment: '254 320 ₽',
  },
]

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

function ApplicationStatus({ status, onOpenProfile }) {
  if (status === 'INFO') {
    return <InfoRequiredStatus onOpenProfile={onOpenProfile} />
  }

  if (status === 'SUCCESS') {
    return <ApprovedStatus />
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

function ApprovedStatus() {
  const [selectedOffer, setSelectedOffer] = useState(null)
  const [detailsSent, setDetailsSent] = useState(false)
  const [details, setDetails] = useState({ bankName: '', bic: '', accountNumber: '' })
  const detailsComplete = Object.values(details).every(Boolean)

  const openOffer = (offer) => {
    setSelectedOffer(offer)
    setDetailsSent(false)
  }

  const closeOffer = () => {
    setSelectedOffer(null)
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
      <section className="offers-panel">
        <div className="offers-header">
          <div>
            <div className="offers-header__caption">Заявка одобрена</div>
            <h1>Выберите подходящие условия</h1>
            <p>
              Мы проанализировали предложения и расположили самые выгодные выше.
            </p>
          </div>
          <div className="offers-header__count">3 предложения</div>
        </div>

        <div className="credit-offers">
          {creditOffers.map((offer, index) => (
            <article
              className={index === 0 ? 'credit-offer credit-offer_best' : 'credit-offer'}
              key={offer.id}
            >
              <div className="credit-offer__top">
                <span className="credit-offer__rank">{index + 1}</span>
                <span className="credit-offer__title">{offer.title}</span>
                {index === 0 && <span className="credit-offer__badge">Лучший выбор</span>}
              </div>

              <div className="credit-offer__amount">{offer.amount}</div>
              <div className="credit-offer__amount-label">сумма кредита</div>

              <dl className="credit-offer__terms">
                <div>
                  <dt>Ставка</dt>
                  <dd>{offer.rate}</dd>
                </div>
                <div>
                  <dt>Срок</dt>
                  <dd>{offer.term}</dd>
                </div>
                <div>
                  <dt>Платёж в месяц</dt>
                  <dd>{offer.payment}</dd>
                </div>
              </dl>

              <Button
                type="button"
                view={index === 0 ? 'accent' : 'secondary'}
                size={48}
                block
                onClick={() => openOffer(offer)}
              >
                Выбрать предложение
              </Button>
            </article>
          ))}
        </div>
      </section>

      <Modal
        open={Boolean(selectedOffer)}
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
                <span>{selectedOffer?.title}</span>
                <strong>{selectedOffer?.amount}</strong>
                <small>
                  {selectedOffer?.rate} · {selectedOffer?.term}
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
        </div>
      </article>

      <div className="status-note">
        <span className="status-note__icon">i</span>
        <p>Когда проверка завершится, её результат появится на этой странице.</p>
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
