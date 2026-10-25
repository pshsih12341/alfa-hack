import { useState } from 'react'
import { Button } from '@alfalab/core-components-button'
import { getCreditPurposeLabel } from '../../data/creditPurposes'

const statusLabels = {
  PRESCORING: 'Прескоринг',
  SCORING: 'Скоринг',
  INFO: 'Нужны данные',
  SUCCESS: 'Одобрено',
  OFFER: 'Есть предложение',
  AWAITING_DISBURSEMENT: 'Ожидает выдачи',
  COMPLETED: 'Исполнена',
  REJECTED: 'Отклонено',
}

const formatMoney = (value) =>
  value ? `${new Intl.NumberFormat('ru-RU').format(value)} ₽` : '—'

const formatDate = (value) =>
  new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))

const formatShortDate = (value) =>
  new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(value))

function AdminApplicationDetails({ application, onBack, onComplete }) {
  const [completing, setCompleting] = useState(false)
  const hasDecision = ['SUCCESS', 'AWAITING_DISBURSEMENT', 'COMPLETED'].includes(
    application.status,
  )

  const completeApplication = async () => {
    setCompleting(true)
    try {
      await onComplete(application.id)
    } finally {
      setCompleting(false)
    }
  }

  return (
    <section className="admin-application-details">
      <Button type="button" view="transparent" size={40} onClick={onBack}>
        ← Все заявки
      </Button>

      <header className="admin-details-heading">
        <div>
          <span>Заявка</span>
          <h1>{application.id.slice(0, 8)}</h1>
          <code>{application.id}</code>
        </div>
        <span className={`admin-status admin-status_${application.status.toLowerCase()}`}>
          {statusLabels[application.status] || application.status}
        </span>
      </header>

      {application.status === 'AWAITING_DISBURSEMENT' && (
        <article className="admin-complete-action admin-complete-action_top">
          <div>
            <strong>Проверьте платёжные поручения</strong>
            <p>
              После фактической выдачи средств отметьте заявку исполненной.
            </p>
          </div>
          <Button
            type="button"
            view="accent"
            size={48}
            disabled={completing}
            onClick={completeApplication}
          >
            {completing ? 'Сохраняем…' : 'Заявка исполнена'}
          </Button>
        </article>
      )}

      <div className="admin-details-grid">
        <article className="admin-details-card">
          <h2>Данные клиента</h2>
          <dl>
            <DetailsRow label="Клиент" value={application.clientName} />
            <DetailsRow label="Client ID" value={application.clientId} mono />
            <DetailsRow label="Телефон" value={application.phoneNumber} />
            <DetailsRow label="ИНН" value={application.inn} />
          </dl>
        </article>

        <article className="admin-details-card">
          <h2>Параметры заявки</h2>
          <dl>
            <DetailsRow label="Цель" value={getCreditPurposeLabel(application.purpose)} />
            <DetailsRow label="Запрошенная сумма" value={formatMoney(application.creditSum)} />
            <DetailsRow label="Создана" value={formatDate(application.createdAt)} />
            <DetailsRow label="Обновлена" value={formatDate(application.updatedAt)} />
          </dl>
        </article>

        {hasDecision && (
          <article className="admin-details-card admin-details-card_wide admin-details-card_payment">
            <h2>Решение</h2>
            <dl>
              <DetailsRow label="Продукт" value={application.product?.product} />
              <DetailsRow
                label="Одобренный лимит"
                value={formatMoney(application.approvedLimit)}
              />
              <DetailsRow
                label="Ставка"
                value={application.product ? `${application.product.rate}% годовых` : '—'}
              />
            </dl>
          </article>
        )}

        {application.paymentOrders?.length > 0 && (
          <article className="admin-details-card admin-details-card_wide">
            <div className="admin-details-card__heading">
              <div>
                <h2>Платёжные поручения</h2>
                <p>Документы, подготовленные бэкендом для выдачи кредита.</p>
              </div>
              <span>{application.paymentOrders.length} документа</span>
            </div>

            <div className="admin-payment-orders">
              {application.paymentOrders.map((payment) => (
                <div className="admin-payment-order" key={payment.id}>
                  <div className="admin-payment-order__number">
                    <span>Платёжное поручение</span>
                    <strong>№ {payment.number}</strong>
                  </div>
                  <div>
                    <span>Дата</span>
                    <strong>{formatShortDate(payment.date)}</strong>
                  </div>
                  <div>
                    <span>Получатель</span>
                    <strong>{payment.recipient}</strong>
                    <small>{payment.recipientAccount}</small>
                  </div>
                  <div className="admin-payment-order__amount">
                    <span>Сумма</span>
                    <strong>{formatMoney(payment.amount)}</strong>
                  </div>
                </div>
              ))}
            </div>
          </article>
        )}

        {application.status === 'COMPLETED' && (
          <div className="admin-completed-message admin-details-card_wide">
            <span>✓</span>
            <div>
              <strong>Заявка исполнена</strong>
              <p>Выдача средств подтверждена.</p>
            </div>
          </div>
        )}

        <article className="admin-details-card admin-details-card_wide admin-details-card_history">
          <h2>История статуса</h2>
          <div className="admin-status-history">
            {application.statusHistory.map((historyItem, index) => (
              <div
                className={index === application.statusHistory.length - 1 ? 'active' : undefined}
                key={`${historyItem.status}-${historyItem.createdAt}`}
              >
                <i />
                <span>
                  <strong>{statusLabels[historyItem.status] || historyItem.status}</strong>
                  <small>{formatDate(historyItem.createdAt)}</small>
                </span>
              </div>
            ))}
          </div>
        </article>
      </div>
    </section>
  )
}

function DetailsRow({ label, value, mono = false }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className={mono ? 'mono' : undefined}>{value || '—'}</dd>
    </div>
  )
}

export default AdminApplicationDetails
