export const creditPurposeOptions = [
  { key: 'property_purchase', content: 'Покупка имущества' },
  { key: 'equipment_purchase', content: 'Покупка оборудования' },
  { key: 'repair', content: 'Ремонт' },
  { key: 'current_expenses', content: 'Текущие расходы' },
  { key: 'working_capital', content: 'Пополнение оборотных средств' },
  { key: 'real_estate_purchase', content: 'Покупка недвижимости' },
  { key: 'other', content: 'Другая цель' },
]

export const getCreditPurpose = (key) => {
  return creditPurposeOptions.find((option) => option.key === key)?.content || ''
}
