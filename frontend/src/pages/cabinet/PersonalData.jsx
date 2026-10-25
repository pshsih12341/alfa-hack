import { useEffect, useRef, useState } from 'react'
import { Button } from '@alfalab/core-components-button'
import { Input } from '@alfalab/core-components-input'
import './PersonalData.css'

const initialExtraData = {
  actualAddress: '',
  employeesCount: '',
  website: '',
  activityDescription: '',
}

function PersonalData({ data, status, shouldScrollToAdditionalData }) {
  const [extraData, setExtraData] = useState(initialExtraData)
  const [sent, setSent] = useState(false)
  const additionalDataRef = useRef(null)
  const extraDataComplete = Object.values(extraData).every(Boolean)

  useEffect(() => {
    if (shouldScrollToAdditionalData) {
      additionalDataRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [shouldScrollToAdditionalData])

  const setField = (field, value) => {
    setSent(false)
    setExtraData((current) => ({ ...current, [field]: value }))
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    setSent(true)
  }

  return (
    <div className="personal-data-page">
      <section className="personal-data-card">
        <div className="personal-data-heading">
          <span>Анкета</span>
          <h1>Личные данные</h1>
          <p>Данные из заявки. Изменить их после отправки нельзя.</p>
        </div>

        <dl className="personal-data-list">
          <DataRow label="Номер телефона" value={data.phoneNumber} />
          <DataRow label="ИНН" value={data.inn} />
        </dl>
      </section>

      {status === 'INFO' && (
        <section
          className="additional-data-card"
          ref={additionalDataRef}
        >
          <div className="additional-data-heading">
            <span>Нужны дополнительные сведения</span>
            <h2>Расскажите о бизнесе подробнее</h2>
            <p>Это поможет нам продолжить рассмотрение заявки.</p>
          </div>

          {sent ? (
            <div className="additional-data-success">
              <span>✓</span>
              <div>
                <strong>Данные отправлены</strong>
                <p>Мы вернулись к рассмотрению заявки.</p>
              </div>
            </div>
          ) : (
            <form className="additional-data-form" onSubmit={handleSubmit}>
              <Input
                block
                size={56}
                label={<RequiredLabel>Фактический адрес</RequiredLabel>}
                value={extraData.actualAddress}
                onChange={(_, { value }) => setField('actualAddress', value)}
                required
              />
              <Input
                block
                size={56}
                label={<RequiredLabel>Количество сотрудников</RequiredLabel>}
                value={extraData.employeesCount}
                onChange={(_, { value }) =>
                  setField('employeesCount', value.replace(/\D/g, '').slice(0, 6))
                }
                inputMode="numeric"
                required
              />
              <Input
                block
                size={56}
                label={<RequiredLabel>Сайт компании</RequiredLabel>}
                value={extraData.website}
                onChange={(_, { value }) => setField('website', value)}
                required
              />
              <Input
                block
                size={56}
                label={<RequiredLabel>Чем занимается компания</RequiredLabel>}
                value={extraData.activityDescription}
                onChange={(_, { value }) => setField('activityDescription', value)}
                required
              />

              <Button
                type="submit"
                view="accent"
                size={56}
                block
                disabled={!extraDataComplete}
              >
                Отправить данные
              </Button>
            </form>
          )}
        </section>
      )}
    </div>
  )
}

function RequiredLabel({ children }) {
  return (
    <>
      {children} <span className="required-mark">*</span>
    </>
  )
}

function DataRow({ label, value }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value || '—'}</dd>
    </div>
  )
}

export default PersonalData
