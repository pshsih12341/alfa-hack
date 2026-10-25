import alfaBankLogo from '../assets/alfa-bank.svg'
import './Logo.css'

function Logo() {
  return (
    <div className="logo" aria-label="Альфа-Банк">
      <img className="logo__image" src={alfaBankLogo} alt="" />
      <span>Альфа-Банк</span>
    </div>
  )
}

export default Logo
