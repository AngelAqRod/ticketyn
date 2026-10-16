import { useRef, useState } from 'react'
import { FileText } from 'lucide-react'
import { downloadFile } from '../api/client'
import { FeedbackMessage } from './FeedbackMessage'

export function InternalTicketReportDownload({ id, reference }: { id: number; reference: string }) {
  const pending = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function download() {
    if (pending.current) return
    pending.current = true; setBusy(true); setError(null)
    try {
      const query = new URLSearchParams({ timezone: Intl.DateTimeFormat().resolvedOptions().timeZone })
      await downloadFile(`/api/internal-tickets/${id}/reports/internal/pdf?${query}`, `Ticket_Interno_${reference}.pdf`)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'No se pudo generar el reporte del ticket.')
    } finally { pending.current = false; setBusy(false) }
  }
  return <div><button type="button" className="button-secondary" disabled={busy} onClick={() => void download()}><FileText size={16} aria-hidden="true" />{busy ? 'Generando PDF...' : 'Exportar PDF'}</button>{error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}</div>
}
