import { useState } from 'react'
import { AmountInput } from '@alfalab/core-components-amount-input'
import { Button } from '@alfalab/core-components-button'
import { Input } from '@alfalab/core-components-input'
import { PhoneInput } from '@alfalab/core-components-phone-input'
import { Select } from '@alfalab/core-components-select'
import Logo from '../components/Logo'
import { creditPurposeOptions } from '../data/creditPurposes'
import './RegistrationPage.css'

const initialForm = {
  phoneNumber: '',
  creditSum: null,
  purpose: '',
  termMonths: 24,
  inn: '',
  bkiConsent: false,
}

const termOptions = [6, 12, 18, 24, 30, 36].map((months) => ({
  key: String(months),
  content: `${months} месяцев`,
}))

function RegistrationPage({ initialMode = 'registration', onAuthenticated }) {
  const [mode, setMode] = useState(initialMode)
  const [form, setForm] = useState(initialForm)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const isFormComplete =
    mode === 'login'
      ? Boolean(form.phoneNumber)
      : Boolean(
          form.phoneNumber &&
            form.creditSum &&
            form.purpose &&
            form.termMonths &&
            form.inn &&
            form.bkiConsent,
        )

  const setField = (field, value) => {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const changeMode = (nextMode) => {
    setMode(nextMode)
    setError('')
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setSubmitting(true)

    try {
      await onAuthenticated(form, mode)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSubmitting(false)
    }
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

            {error && <div className="form-error">{error}</div>}

            <Button
              className="submit-button"
              type="submit"
              view="accent"
              size={56}
              block
              disabled={!isFormComplete || submitting}
            >
              {submitting
                ? 'Отправляем…'
                : mode === 'registration'
                  ? 'Отправить заявку'
                  : 'Войти'}
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
        onChange={({ selected }) => setField('purpose', selected?.key ?? '')}
      />

      <Select
        block
        size={56}
        label="Срок кредита"
        options={termOptions}
        selected={String(form.termMonths)}
        onChange={({ selected }) =>
          setField('termMonths', Number(selected?.key || 24))
        }
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

      <label className="bki-consent">
        <input
          type="checkbox"
          checked={form.bkiConsent}
          onChange={(event) => setField('bkiConsent', event.target.checked)}
        />
        <span>Согласен на запрос кредитной истории в БКИ</span>
      </label>
    </>
  )
}

export default RegistrationPage
