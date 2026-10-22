export const creditPurposeOptions = [
  { key: 'working_capital', content: 'Пополнение оборотных средств' },
  { key: 'equipment', content: 'Покупка оборудования' },
  { key: 'real_estate', content: 'Покупка недвижимости' },
  { key: 'refinancing', content: 'Рефинансирование' },
  { key: 'other', content: 'Другая цель' },
]

export const getCreditPurpose = (key, customPurpose = '') => {
  if (key === 'other') return customPurpose

  return creditPurposeOptions.find((option) => option.key === key)?.content || ''
}
