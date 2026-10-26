export const creditPurposeOptions = [
  { key: 'real_estate', content: 'Покупка недвижимости' },
  { key: 'property', content: 'Покупка имущества' },
  { key: 'equipment', content: 'Покупка оборудования' },
  { key: 'repair', content: 'Ремонт' },
  { key: 'current_expenses', content: 'Текущие расходы' },
  { key: 'working_capital', content: 'Пополнение оборотных средств' },
  { key: 'refinancing', content: 'Рефинансирование' },
]

export const getCreditPurpose = (key) => {
  return creditPurposeOptions.find((option) => option.key === key)?.content || ''
}

export const getCreditPurposeLabel = (key) => getCreditPurpose(key) || key
