import { useState } from 'react'
import { AmountInput } from '@alfalab/core-components-amount-input'
import { Button } from '@alfalab/core-components-button'
import { Input } from '@alfalab/core-components-input'
import { PhoneInput } from '@alfalab/core-components-phone-input'
import { Select } from '@alfalab/core-components-select'
import Logo from '../components/Logo'
import { creditPurposeOptions, getCreditPurpose } from '../data/creditPurposes'
import './RegistrationPage.css'

const initialForm = {
  phoneNumber: '',
  creditSum: null,
  purpose: '',
  customPurpose: '',
  income: null,
  inn: '',
}

function RegistrationPage({ initialMode = 'registration', onAuthenticated }) {
  const [mode, setMode] = useState(initialMode)
  const [form, setForm] = useState(initialForm)
  const isFormComplete =
    mode === 'login'
      ? Boolean(form.phoneNumber)
      : Boolean(
          form.phoneNumber &&
            form.creditSum &&
            form.purpose &&
            form.income &&
            form.inn &&
            (form.purpose !== 'other' || form.customPurpose),
        )

  const setField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const changeMode = (nextMode) => {
    setMode(nextMode)
  }

  const handleSubmit = (event) => {
    event.preventDefault()

    if (mode === 'login') {
      onAuthenticated({ phoneNumber: form.phoneNumber })
      return
    }

    onAuthenticated({
      ...form,
      purpose: getCreditPurpose(form.purpose, form.customPurpose),
    })
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

        <div className="auth-switch">
          <button
            type="button"
            className={mode === 'login' ? 'auth-switch__button active' : 'auth-switch__button'}
            onClick={() => changeMode('login')}
          >
            Вход
          </button>
          <button
            type="button"
            className={mode === 'registration' ? 'auth-switch__button active' : 'auth-switch__button'}
            onClick={() => changeMode('registration')}
          >
            Регистрация
          </button>
        </div>

        <div className="form-shell">
          <header className="form-header">
            <div className="step">
              {mode === 'registration' ? 'Шаг 1 из 3' : 'Личный кабинет'}
            </div>
            <h2>
              {mode === 'registration' ? 'Заполните данные' : 'Войдите в аккаунт'}
            </h2>
            <p>
              {mode === 'registration'
                ? 'И мы предложим лучшие условия для вашего бизнеса'
                : 'Введите номер телефона, который указывали при регистрации'}
            </p>
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

            {mode === 'registration' && (
              <RegistrationFields form={form} setField={setField} />
            )}

            <Button
              className="submit-button"
              type="submit"
              view="accent"
              size={56}
              block
              disabled={!isFormComplete}
            >
              {mode === 'registration' ? 'Отправить заявку' : 'Войти'}
            </Button>

            {mode === 'registration' && (
              <p className="legal">
                Нажимая кнопку, вы соглашаетесь на обработку персональных
                данных.
              </p>
            )}
          </form>
        </div>
      </section>
    </main>
  )
}

function RegistrationFields({ form, setField }) {
  return (
    <>
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
        options={creditPurposeOptions}
        selected={form.purpose || null}
        onChange={({ selected }) => {
          const purpose = selected?.key ?? ''
          setField('purpose', purpose)

          if (purpose !== 'other') {
            setField('customPurpose', '')
          }
        }}
      />

      {form.purpose === 'other' && (
        <Input
          block
          size={56}
          label="Укажите цель кредита"
          value={form.customPurpose}
          onChange={(_, { value }) => setField('customPurpose', value)}
          required
        />
      )}

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
    </>
  )
}

export default RegistrationPage
