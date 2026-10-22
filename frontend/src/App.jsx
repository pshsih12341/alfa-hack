import { useState } from 'react'
import { AmountInput } from '@alfalab/core-components-amount-input'
import { Button } from '@alfalab/core-components-button'
import { Input } from '@alfalab/core-components-input'
import { PhoneInput } from '@alfalab/core-components-phone-input'
import { Select } from '@alfalab/core-components-select'
import './App.css'

const purposeOptions = [
  { key: 'working_capital', content: 'Пополнение оборотных средств' },
  { key: 'equipment', content: 'Покупка оборудования' },
  { key: 'real_estate', content: 'Покупка недвижимости' },
  { key: 'refinancing', content: 'Рефинансирование' },
  { key: 'other', content: 'Другая цель' },
]

const initialForm = {
  phoneNumber: '',
  creditSum: null,
  purpose: '',
  income: null,
  inn: '',
}

function Logo() {
  return (
    <div className="logo" aria-label="Альфа-Банк">
      <span className="logo__sign" aria-hidden="true">
        <i />
        <i />
      </span>
      <span>Альфа-Банк</span>
    </div>
  )
}

function App() {
  const [form, setForm] = useState(initialForm)
  const [submitted, setSubmitted] = useState(false)
  const isFormComplete = Object.values(form).every(Boolean)

  const setField = (field, value) => {
    setSubmitted(false)
    setForm((current) => ({ ...current, [field]: value }))
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    setSubmitted(true)
  }

  return (
    <main className="registration-page">
      <section className="intro">
        <Logo />

        <div className="intro__content">
          <div className="intro__eyebrow">Кредит для бизнеса</div>
          <h1>Деньги для важных решений</h1>
          <p>
            Заполните короткую анкету — подберём предложение под задачи
            вашего бизнеса.
          </p>
        </div>

        <div className="intro__note">Решение онлайн без визита в офис</div>
      </section>

      <section className="form-side">
        <div className="mobile-header">
          <Logo />
          <span>Кредит для бизнеса</span>
        </div>

        <div className="form-shell">
          <header className="form-header">
            <div className="step">Шаг 1 из 3</div>
            <h2>Заполните данные</h2>
            <p>И мы предложим лучшие условия для вашего бизнеса</p>
          </header>

          <form className="form" onSubmit={handleSubmit}>
            <PhoneInput
              block
              size={56}
              label="Номер телефона"
              value={form.phoneNumber}
              onChange={(_, { value }) => setField('phoneNumber', value)}
              clearableCountryCode
              required
            />

            <AmountInput
              block
              size={56}
              label="Желаемая сумма кредита"
              value={form.creditSum}
              onChange={(_, { value }) => setField('creditSum', value)}
              currency="RUR"
              integersOnly
              required
            />

            <Select
              block
              size={56}
              label="Цель кредита"
              placeholder="Выберите цель"
              options={purposeOptions}
              selected={form.purpose || null}
              onChange={({ selected }) =>
                setField('purpose', selected?.key ?? '')
              }
              nativeSelect
            />

            <AmountInput
              block
              size={56}
              label="Среднемесячный доход"
              value={form.income}
              onChange={(_, { value }) => setField('income', value)}
              currency="RUR"
              integersOnly
              required
            />

            <Input
              block
              size={56}
              label="ИНН"
              value={form.inn}
              onChange={(_, { value }) =>
                setField('inn', value.replace(/\D/g, '').slice(0, 12))
              }
              inputMode="numeric"
              maxLength={12}
              required
            />

            <Button
              className="submit-button"
              type="submit"
              view="accent"
              size={56}
              block
              disabled={!isFormComplete}
            >
              Отправить заявку
            </Button>

            {submitted && (
              <div className="success-message">
                <span className="success-message__icon">✓</span>
                <div>
                  <strong>Данные приняты</strong>
                  <p>Пока это демо — заявка никуда не отправлена.</p>
                </div>
              </div>
            )}

            <p className="legal">
              Нажимая кнопку, вы соглашаетесь на обработку персональных
              данных.
            </p>
          </form>
        </div>
      </section>
    </main>
  )
}

export default App
