import { useEffect, useState, type FormEvent } from 'react'
import { getReceptionFilters, installationError, saveReceptionFilters } from '../api/installationOrders'

const lines = (text: string) => text.split('\n').map(line => line.trim()).filter(Boolean)

export function ReceptionFiltersSettings() {
  const [senders, setSenders] = useState(''), [subjects, setSubjects] = useState('')
  const [loading, setLoading] = useState(true), [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null), [success, setSuccess] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    getReceptionFilters(controller.signal).then(value => {
      if (controller.signal.aborted) return
      setSenders(value.senders.join('\n')); setSubjects(value.subjects.join('\n')); setLoading(false)
    }).catch(cause => { if (!controller.signal.aborted) { setError(installationError(cause)); setLoading(false) } })
    return () => controller.abort()
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true); setError(null); setSuccess(false)
    try {
      const value = await saveReceptionFilters({ senders: lines(senders), subjects: lines(subjects) })
      setSenders(value.senders.join('\n')); setSubjects(value.subjects.join('\n')); setSuccess(true)
    } catch (cause) { setError(installationError(cause)) } finally { setSaving(false) }
  }

  const from = lines(senders), about = lines(subjects)
  if (loading) return <p role="status" className="text-xs font-mono text-slate-400">Consultando filtros…</p>
  return <form onSubmit={submit} className="space-y-4">
    <p className="text-sm text-slate-300">
      Las órdenes se reciben {from.length ? `de ${from.join(', ')}` : 'de cualquier remitente'}
      {about.length ? ` con asunto que contenga ${about.map(word => `«${word}»`).join(' o ')}` : ' con cualquier asunto'}.
      Los demás correos no se tratan como solicitudes de orden: quedan como «Descartada» en la bandeja.
    </p>
    <label className="block text-xs font-mono font-semibold text-slate-300">Remitentes permitidos (uno por línea)
      <textarea className="form-input font-mono mt-1.5 text-xs" rows={4} value={senders} disabled={saving} placeholder={'ventas@cliente.com\n@empresa.com'} onChange={e => { setSenders(e.target.value); setSuccess(false) }} />
    </label>
    <label className="block text-xs font-mono font-semibold text-slate-300">Palabras del asunto (una por línea; basta que aparezca una)
      <textarea className="form-input font-mono mt-1.5 text-xs" rows={4} value={subjects} disabled={saving} placeholder="instalación" onChange={e => { setSubjects(e.target.value); setSuccess(false) }} />
    </label>
    <p className="text-xs font-mono text-slate-500">Vacío acepta todo. Un dominio se escribe como @empresa.com. El remitente de un correo puede falsificarse.</p>
    {error && <p role="alert" className="text-xs font-mono text-red-300">{error}</p>}
    {success && <p role="status" className="text-xs font-mono text-emerald-300">Filtros guardados. Se aplican desde la próxima consulta de correo.</p>}
    <button className="button-primary rounded-full font-mono text-xs px-5 py-2" disabled={saving}>{saving ? 'Guardando…' : 'Guardar'}</button>
  </form>
}
