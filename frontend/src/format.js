// Общие форматтеры и проверки: те же правила, что на бэкенде и в ML-сервисе.

export const CREDIT_SUM_MIN = 100_000
export const CREDIT_SUM_MAX = 30_000_000

export const formatMoney = (value) =>
  `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value)} ₽`

// 17.5 → «17,5%», 18 → «18%»
export const formatRate = (value) =>
  `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value)}%`

// 1 месяц, 24 месяца, 36 месяцев
export const formatMonths = (value) => {
  const lastTwo = value % 100
  const last = value % 10
  if (lastTwo >= 11 && lastTwo <= 14) return `${value} месяцев`
  if (last === 1) return `${value} месяц`
  if (last >= 2 && last <= 4) return `${value} месяца`
  return `${value} месяцев`
}

export const termOptions = [6, 12, 18, 24, 30, 36].map((months) => ({
  key: String(months),
  content: formatMonths(months),
}))

const checkDigit = (digits, weights) =>
  (weights.reduce((sum, weight, index) => sum + weight * digits[index], 0) % 11) % 10

// 10 цифр — организация, 12 — ИП; контрольные цифры должны сойтись.
export const isValidInn = (inn) => {
  if (!/^\d{10}$|^\d{12}$/.test(inn)) return false
  const digits = [...inn].map(Number)
  if (digits.length === 10) {
    return checkDigit(digits, [2, 4, 10, 3, 5, 9, 4, 6, 8]) === digits[9]
  }
  return (
    checkDigit(digits, [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === digits[10] &&
    checkDigit(digits, [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === digits[11]
  )
}

// Ошибка суммы для формы; null — сумма подходит или ещё не введена.
export const creditSumError = (rubles) => {
  if (!rubles) return null
  if (rubles < CREDIT_SUM_MIN || rubles > CREDIT_SUM_MAX) {
    return `Сумма кредита — от ${formatMoney(CREDIT_SUM_MIN)} до ${formatMoney(CREDIT_SUM_MAX)}`
  }
  return null
}

export const innError = (inn) => {
  if (!inn || inn.length < 10) return null
  return isValidInn(inn) ? null : 'Проверьте ИНН: контрольные цифры не сходятся'
}

// Содержимое файла в base64 — так выписки 1С уходят в API.
export const readFileAsBase64 = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
    reader.onerror = () => reject(new Error(`Не удалось прочитать файл ${file.name}`))
    reader.readAsDataURL(file)
  })
