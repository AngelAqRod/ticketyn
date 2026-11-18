import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { PageHeading } from '../components/PageHeading'
import { RequestState } from '../components/RequestState'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { AdminRequestFields, blankValues, payloadFrom, periodInvalid, valuesFrom } from '../components/AdminRequestFields'
import { createAdminRequest, getAdminRequest, updateAdminRequest } from '../api/adminRequests'

export function AdminRequestForm({ edit = false }: { edit?: boolean }) {
  const navigate = useNavigate(), id = Number(useParams().id)
  const [values, setValues] = useState(blankValues), [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(edit), [registered, setRegistered] = useState<string | null>(null), sending = useRef(false)
  useEffect(() => {
    if (!edit) return
    const controller = new AbortController()
    getAdminRequest(id, controller.signal).then(row => { if (!controller.signal.aborted) { setValues(valuesFrom(row)); setRegistered(row.created_at); setLoading(false) } })
      .catch(cause => { if (!controller.signal.aborted) { setError(cause instanceof Error ? cause.message : 'No se pudo cargar la solicitud.'); setLoading(false) } })
    return () => controller.abort()
  }, [edit, id])
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (sending.current) return
    sending.current = true; setBusy(true); setError(null)
    try {
      const saved = edit ? await updateAdminRequest(id, payloadFrom(values)) : await createAdminRequest(payloadFrom(values))
      navigate(`/admin-requests/${saved.id}`)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo guardar la solicitud.') } finally { sending.current = false; setBusy(false) }
  }
  return <>
    <PageHeading title={edit ? 'Editar solicitud administrativa' : 'Registrar solicitud administrativa'} description="Bitácora de requerimientos recibidos. Los registros asociados se vinculan desde el detalle." theme="purple"
      action={<Link className="button-secondary" to={edit ? `/admin-requests/${id}` : '/admin-requests'}>Volver</Link>} />
    <RequestState loading={loading} />
    {!loading && <form className="panel max-w-3xl p-6" onSubmit={submit} aria-label="Solicitud administrativa" aria-busy={busy}>
      <AdminRequestFields value={values} onChange={setValues} disabled={busy} />
      <p className="mt-4 text-xs text-slate-400">{edit && registered ? 'La fecha de registro se conserva y no se puede modificar.' : 'La fecha de registro y el usuario que registra se asignan automáticamente.'}</p>
      {error && <FeedbackMessage variant="error" className="mt-4">{error}</FeedbackMessage>}
      <div className="mt-6"><button className="button-primary button-primary--purple" type="submit" disabled={busy || periodInvalid(values) || !values.requester_id || !values.type_id || !values.description.trim() || !values.request_date}>{busy ? 'Guardando…' : edit ? 'Guardar cambios' : 'Registrar solicitud'}</button></div>
    </form>}
  </>
}
