import './Logo.css'

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

export default Logo
