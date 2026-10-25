import './PersonalData.css'

function PersonalData({ data }) {
  return (
    <div className="personal-data-page">
      <section className="personal-data-card">
        <div className="personal-data-heading">
          <span>Анкета</span>
          <h1>Личные данные</h1>
          <p>Данные из регистрации. Изменить их после отправки нельзя.</p>
        </div>

        <dl className="personal-data-list">
          <DataRow label="Номер телефона" value={data.phoneNumber} />
          <DataRow label="ИНН" value={data.inn} />
        </dl>
      </section>
    </div>
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
