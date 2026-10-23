import '../styles/distribution.css'
import { Link, useLocation } from 'react-router'
import { usePermissions } from '../auth/permissions'

export function CircuitsNavigation() {
  const access = usePermissions()
  const location = useLocation()
  const canSeeDistribution = access.any('distribution_devices.view', 'distribution_devices.lookup')
  const canSeeCircuits = access.any('circuits.view', 'circuits.lookup')

  if (!canSeeDistribution) return null

  const isDistribution = location.pathname.startsWith('/distribution-devices')

  return (
    <nav aria-label="Navegación de enlaces y distribución" className={`mb-4 ${isDistribution ? 'distribution-theme' : ''}`}>
      <div className={`segmented-control segmented-control--${isDistribution ? 'purple' : 'blue'} inline-flex`} role="tablist">
        {canSeeCircuits && (
          <Link
            to="/circuits"
            role="tab"
            aria-selected={!isDistribution}
            aria-pressed={!isDistribution}
            className={`segment-button ${!isDistribution ? 'segment-button--active' : ''}`}
          >
            Circuitos
          </Link>
        )}
        <Link
          to="/distribution-devices"
          role="tab"
          aria-selected={isDistribution}
          aria-pressed={isDistribution}
          className={`segment-button ${isDistribution ? 'segment-button--active' : ''}`}
        >
          Equipos de distribución
        </Link>
      </div>
    </nav>
  )
}
