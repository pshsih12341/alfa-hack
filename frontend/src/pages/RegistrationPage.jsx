import { useState } from 'react'
import { AmountInput } from '@alfalab/core-components-amount-input'
import { Button } from '@alfalab/core-components-button'
import { Input } from '@alfalab/core-components-input'
import { PhoneInput } from '@alfalab/core-components-phone-input'
import { Select } from '@alfalab/core-components-select'
import Logo from '../components/Logo'
import { creditPurposeOptions } from '../data/creditPurposes'
import { creditSumError, innError, isValidInn, termOptions } from '../format'
import './RegistrationPage.css'

const initialForm = {
  phoneNumber: '',
  creditSum: null,
  purpose: '',
  termMonths: 24,
  inn: '',
  bkiConsent: false,
  hasCollateral: false,
  revenue: null,
}

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
            form.bkiConsent &&
            !creditSumError(form.creditSum / 100) &&
            isValidInn(form.inn),
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
        error={creditSumError(form.creditSum / 100) || false}
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
        error={innError(form.inn) || false}
        required
      />

      <AmountInput
        block
        size={56}
        label="Выручка за последние 12 месяцев"
        hint="Необязательно. Укажите, если вашей выручки нет в открытых данных ФНС"
        value={form.revenue}
        onChange={(_, { value }) => setField('revenue', value)}
        currency="RUR"
        integersOnly
      />

      <label className="bki-consent">
        <input
          type="checkbox"
          checked={form.hasCollateral}
          onChange={(event) => setField('hasCollateral', event.target.checked)}
        />
        <span>Готов предоставить залог — ставка ниже, окончательные условия после оценки залога</span>
      </label>

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
