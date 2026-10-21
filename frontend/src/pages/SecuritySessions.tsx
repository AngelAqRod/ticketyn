import { useState } from 'react'
import { PageHeading } from '../components/PageHeading'
import { SessionsPanel, type SessionsStats } from '../components/SessionsPanel'
import { RefreshCw } from 'lucide-react'

export function SecuritySessions() {
  const [stats, setStats] = useState<SessionsStats | null>(null)
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  return (
    <>
      <PageHeading
        title="Sesiones"
        description="Consulta y revocación de sesiones activas en memoria RAM (SecurityMemory). Al reiniciar el servicio se invalidan automáticamente."
        telemetry={
          stats !== null && (
            <span className="heading-telemetry">
              <span>Activas:</span>
              <strong className="telemetry-value--slate font-bold">{stats.total}</strong>
              {stats.active5m > 0 && (
                <>
                  <span className="text-slate-600">·</span>
                  <span>Últimos 5m:</span>
                  <strong className="text-emerald-400 font-bold">{stats.active5m}</strong>
                </>
              )}
            </span>
          )
        }
        action={
          <button
            type="button"
            className="button-primary button-primary--slate rounded-full shadow-sm"
            onClick={() => setRefreshTrigger(v => v + 1)}
          >
            <RefreshCw size={14} aria-hidden="true" />
            Actualizar sesiones
          </button>
        }
      />
      <SessionsPanel
        administrative
        refreshSignal={refreshTrigger}
        onStatsChange={setStats}
      />
    </>
  )
}
