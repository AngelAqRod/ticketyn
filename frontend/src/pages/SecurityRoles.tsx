import { useEffect, useRef, useState } from 'react'
import { getJson, postJson, patchJson, deleteResource } from '../api/client'
import { allPages, type SecurityRole, type Permission } from '../api/security'
import { useAuth } from '../auth/context'
import { PageHeading } from '../components/PageHeading'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { RequestState } from '../components/RequestState'
import { Plus, ShieldCheck } from 'lucide-react'

interface Draft { id: number | null; name: string; description: string; permissions: string[]; editable: boolean }
const empty = (): Draft => ({ id: null, name: '', description: '', permissions: [], editable: true })
export function SecurityRoles() {
  const auth = useAuth()
  const [roles, setRoles] = useState<SecurityRole[]>([]), [permissions, setPermissions] = useState<Permission[]>([])
  const [draft, setDraft] = useState<Draft | null>(null), [saved, setSaved] = useState(''), [copy, setCopy] = useState<number | null>(null)
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null), [notice, setNotice] = useState(''), [retry, setRetry] = useState(0)
  const [compare, setCompare] = useState('')
  const sending = useRef(false)
  const dirty = !!draft && JSON.stringify(draft) !== saved
  useEffect(() => {
    const c = new AbortController(); setLoading(true); setError(null)
    Promise.all([allPages<SecurityRole>('/api/security/roles', c.signal), getJson<Permission[]>('/api/security/permissions', c.signal)]).then(([r, p]) => { if (!c.signal.aborted) { setRoles(r); setPermissions(p) } }).catch(e => { if (!c.signal.aborted) setError(e instanceof Error ? e.message : 'No se pudieron cargar los roles') }).finally(() => { if (!c.signal.aborted) setLoading(false) })
    return () => c.abort()
  }, [retry])
  useEffect(() => {
    if (!dirty) return
    const unload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    const click = (e: MouseEvent) => { const link = (e.target as Element).closest?.('a[href]'); if (link && !window.confirm('Hay cambios sin guardar. ¿Salir del editor de roles?')) { e.preventDefault(); e.stopPropagation() } }
    window.addEventListener('beforeunload', unload); document.addEventListener('click', click, true)
    return () => { window.removeEventListener('beforeunload', unload); document.removeEventListener('click', click, true) }
  }, [dirty])
  function edit(role?: SecurityRole, duplicate = false) {
    if (dirty && !window.confirm('Hay cambios sin guardar. ¿Descartarlos?')) return
    const data = role ? { id: duplicate ? null : role.id, name: duplicate ? `${role.name} (copia)` : role.name, description: role.description ?? '', permissions: role.permissions, editable: duplicate || role.editable } : empty()
    setDraft(data); setSaved(JSON.stringify(data)); setCopy(duplicate && role ? role.id : null); setCompare(''); setError(null); setNotice('')
  }
  // Dependencies come exclusively from the backend registry, not a second matrix.
  function selectCodes(codes: string[], enabled: boolean) {
    if (!draft) return
    const next = new Set(draft.permissions)
    if (enabled) {
      const add = (code: string) => { const p = permissions.find(p => p.code === code); if (!p || p.exclusive || next.has(code)) return; next.add(code); p.requires.forEach(add) }
      codes.forEach(add)
    } else {
      codes.forEach(code => next.delete(code))
      let changed = true
      while (changed) { changed = false; for (const p of permissions) if (next.has(p.code) && p.requires.some(code => !next.has(code))) { next.delete(p.code); changed = true } }
    }
    setDraft({ ...draft, permissions: [...next].sort() })
  }
  async function save() {
    if (!draft || sending.current) return
    sending.current = true; setBusy(true); setError(null); setNotice('')
    try {
      const data = draft.id === null
        ? await postJson<SecurityRole>(copy === null ? '/api/security/roles' : `/api/security/roles/${copy}/duplicate`, { name: draft.name, description: draft.description || null })
        : await patchJson<SecurityRole>(`/api/security/roles/${draft.id}`, { name: draft.name, description: draft.description || null, permissions: draft.permissions })
      // New roles deliberately start empty; copies retain their independent source grants.
      const next = { id: data.id, name: data.name, description: data.description ?? '', permissions: data.permissions, editable: data.editable }
      setDraft(next); setSaved(JSON.stringify(next)); setCopy(null); setRetry(r => r + 1); setNotice('Rol guardado correctamente.'); await auth?.refresh()
    } catch (e) { setError(e instanceof Error ? e.message : 'No se pudo guardar el rol') }
    finally { sending.current = false; setBusy(false) }
  }
  async function remove(role: SecurityRole) {
    if (sending.current || !window.confirm(`¿Eliminar el rol ${role.name}? Solo es posible si no tiene Responsables asignados.`)) return
    sending.current = true; setBusy(true); setError(null)
    try { await deleteResource(`/api/security/roles/${role.id}`); setDraft(null); setRetry(r => r + 1); setNotice('Rol eliminado.') }
    catch (e) { setError(e instanceof Error ? e.message : 'No se pudo eliminar el rol') }
    finally { sending.current = false; setBusy(false) }
  }
  const modules = [...new Set(permissions.map(p => p.module))]
  const comparison = roles.find(r => String(r.id) === compare)
  return <>
    <PageHeading
      title="Roles y permisos"
      description="Definiciones de acceso y permisos. Los roles predeterminados del sistema conservan sus permisos fijos."
      telemetry={
        !loading && roles.length > 0 && (
          <span className="heading-telemetry">
            <span>Total:</span>
            <strong className="telemetry-value--slate font-bold">{roles.length}</strong>
            {roles.some(r => r.code) && (
              <>
                <span className="text-slate-600">·</span>
                <span>Predeterminados:</span>
                <strong className="text-sky-400 font-bold">{roles.filter(r => r.code).length}</strong>
              </>
            )}
            {roles.some(r => !r.code) && (
              <>
                <span className="text-slate-600">·</span>
                <span>Personalizados:</span>
                <strong className="text-amber-400 font-bold">{roles.filter(r => !r.code).length}</strong>
              </>
            )}
          </span>
        )
      }
      action={
        <button
          type="button"
          className="button-primary button-primary--slate rounded-full shadow-sm"
          disabled={busy || loading}
          onClick={() => edit()}
        >
          <Plus size={15} aria-hidden="true" />
          Nuevo rol personalizado
        </button>
      }
    />
    {notice && <FeedbackMessage variant="success" className="mb-4">{notice}</FeedbackMessage>}
    {error && <FeedbackMessage variant="error" className="mb-4">{error}</FeedbackMessage>}
    <RequestState loading={loading} error={null} />
    {draft && (
      <form
        className="form-surface mb-5 p-6 rounded-2xl bg-[#0b1426] border border-slate-700/60 shadow-xl space-y-4"
        aria-label="Editor de rol"
        onSubmit={e => { e.preventDefault(); void save() }}
      >
        <div className="flex items-center gap-2 border-b border-slate-700/60 pb-2.5 mb-4">
          <span
            className="flex h-6 w-6 items-center justify-center rounded-lg bg-slate-800/80 border border-slate-700/80 text-slate-300 text-xs"
            aria-hidden="true"
          >
            <ShieldCheck size={13} />
          </span>
          <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
            {copy !== null ? 'Duplicar rol' : draft.id === null ? 'Nuevo rol personalizado' : draft.editable ? 'Editar rol' : 'Consultar rol predeterminado'}
          </h2>
        </div>
        <fieldset disabled={busy || !draft.editable} className="grid gap-3 sm:grid-cols-2">
          <label className="block text-xs font-semibold text-slate-300">
            Nombre del rol
            <input
              className="form-input mt-1"
              required
              maxLength={200}
              value={draft.name}
              onChange={e => setDraft({ ...draft, name: e.target.value })}
            />
          </label>
          <label className="block text-xs font-semibold text-slate-300">
            Descripción
            <input
              className="form-input mt-1"
              maxLength={5000}
              value={draft.description}
              onChange={e => setDraft({ ...draft, description: e.target.value })}
            />
          </label>
        </fieldset>
        {draft.id === null && (
          <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800/90 text-xs font-mono text-slate-300 my-3">
            {copy === null
              ? 'El nuevo rol se crea sin permisos. Después de guardarlo podrás asignarlos.'
              : 'La copia conserva los permisos del origen y podrá modificarse independientemente.'}
          </div>
        )}
        <div className="my-4 space-y-2.5">
          {modules.map(module => {
            const group = permissions.filter(p => p.module === module)
            const selectable = group.filter(p => !p.exclusive)
            const assignedCount = group.filter(p => draft.permissions.includes(p.code)).length
            return (
              <details key={module} className="panel rounded-xl bg-[#070d1a] border border-slate-800/90 overflow-hidden">
                <summary className="cursor-pointer text-xs font-bold font-mono text-slate-200 p-3 hover:bg-slate-800/40 transition-colors flex items-center justify-between">
                  <span>{moduleLabel(module)} · {assignedCount}/{group.length}</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800/80 border border-slate-700/60 text-slate-400">
                    {assignedCount > 0 ? `${assignedCount} activos` : 'Sin permisos'}
                  </span>
                </summary>
                <fieldset disabled={busy || !draft.editable || draft.id === null} className="p-3 pt-2 border-t border-slate-800/80 grid gap-2 sm:grid-cols-2">
                  <label className="flex items-center gap-2 sm:col-span-2 text-xs font-semibold text-slate-200 pb-2 border-b border-slate-800/60">
                    <input
                      type="checkbox"
                      checked={!!selectable.length && selectable.every(p => draft.permissions.includes(p.code))}
                      disabled={!selectable.length}
                      onChange={e => selectCodes(selectable.map(p => p.code), e.target.checked)}
                    />
                    Seleccionar acciones disponibles
                  </label>
                  {group.map(p => (
                    <label key={p.code} className="flex items-start gap-2 text-xs text-slate-300 p-1.5 rounded-lg hover:bg-slate-800/30">
                      <input
                        type="checkbox"
                        disabled={p.exclusive}
                        checked={draft.permissions.includes(p.code)}
                        onChange={e => selectCodes([p.code], e.target.checked)}
                      />
                      <span>
                        <span className="font-medium text-slate-200">{p.label}</span>
                        {p.exclusive && (
                          <span className="block text-[10px] text-amber-400/90 font-mono">Exclusivo del Superadministrador</span>
                        )}
                      </span>
                    </label>
                  ))}
                </fieldset>
              </details>
            )
          })}
        </div>
        <div className="pt-2 border-t border-slate-800/80">
          <label className="block max-w-md text-xs font-semibold text-slate-300">
            Comparar con
            <select
              className="form-input mt-1"
              value={compare}
              onChange={e => setCompare(e.target.value)}
            >
              <option value="">Sin comparación</option>
              {roles.filter(r => r.id !== draft.id).map(r => (
                <option key={r.id} value={r.id}>{r.name}</option>
              ))}
            </select>
          </label>
          {comparison && (
            <ul className="my-3 space-y-1.5 p-3 rounded-xl bg-slate-900/80 border border-slate-800/90 font-mono text-xs text-slate-300">
              {permissions
                .filter(p => draft.permissions.includes(p.code) !== comparison.permissions.includes(p.code))
                .map(p => (
                  <li key={p.code} className="flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                    <span>{moduleLabel(p.module)} · {p.label}:</span>
                    <strong className={draft.permissions.includes(p.code) ? 'text-emerald-400' : 'text-sky-400'}>
                      {draft.permissions.includes(p.code) ? 'Solo en el rol abierto' : `Solo en ${comparison.name}`}
                    </strong>
                  </li>
                ))}
            </ul>
          )}
        </div>
        <div className="mt-4 flex flex-wrap gap-3 pt-2 border-t border-slate-800/80">
          {draft.editable && (
            <button
              type="submit"
              className="button-primary button-primary--slate rounded-full shadow-sm"
              disabled={busy}
            >
              {busy ? 'Guardando…' : 'Guardar rol'}
            </button>
          )}
          <button
            type="button"
            className="button-secondary rounded-full shadow-xs"
            disabled={busy}
            onClick={() => {
              if (!dirty || window.confirm('¿Descartar los cambios sin guardar?')) setDraft(null)
            }}
          >
            Cerrar editor
          </button>
        </div>
      </form>
    )}
    {!loading && (
      <div className="panel table-surface overflow-x-auto rounded-2xl bg-[#0b1426] border table-surface--slate shadow-xl">
        <table className="operation-table min-w-full">
          <caption className="sr-only">Roles de seguridad</caption>
          <thead>
            <tr>
              <th scope="col">Rol</th>
              <th scope="col">Tipo</th>
              <th scope="col">Permisos</th>
              <th scope="col">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {roles.map(role => (
              <tr key={role.id}>
                <td>
                  <span className="font-bold text-white text-sm">{role.name}</span>
                  {role.description && (
                    <p className="text-xs text-slate-400 font-mono mt-0.5">{role.description}</p>
                  )}
                </td>
                <td>
                  <span className={`status-badge ${role.code ? 'status-neutral' : 'status-active'}`}>
                    {role.code ? 'Predeterminado' : 'Personalizado'}
                  </span>
                </td>
                <td>
                  <span className="font-mono text-xs font-bold text-slate-200">
                    {role.permissions.length}
                  </span>
                </td>
                <td>
                  <div className="table-actions">
                    <button
                      type="button"
                      className="button-secondary table-action rounded-full"
                      disabled={busy}
                      onClick={() => edit(role)}
                    >
                      {role.editable ? 'Editar' : 'Consultar'} {role.name}
                    </button>
                    {role.duplicable && (
                      <button
                        type="button"
                        className="button-secondary table-action rounded-full"
                        disabled={busy}
                        onClick={() => edit(role, true)}
                      >
                        Duplicar {role.name}
                      </button>
                    )}
                    {role.editable && (
                      <button
                        type="button"
                        className="button-danger table-action rounded-full"
                        disabled={busy}
                        onClick={() => void remove(role)}
                      >
                        Eliminar {role.name}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </>
}

function moduleLabel(module: string) {
  const labels: Record<string, string> = { dashboard: 'Dashboard', tickets: 'Tickets', internal_tickets: 'Tickets internos', changes: 'Control de cambios', customers: 'Clientes', circuits: 'Circuitos', activations: 'Activaciones FMS', capacity_changes: 'Cambios de capacidad', lifecycle: 'Bajas y reactivaciones', cpe: 'Configuración CPE', roles: 'Roles', accounts: 'Acceso de Responsables', sessions: 'Sesiones', security: 'Seguridad', audit: 'Auditoría', 'catalogs.responsibles': 'Responsables', 'catalogs.positions': 'Puestos', 'catalogs.sectors': 'Sectores', 'catalogs.nodes': 'Nodos', 'catalogs.departments': 'Departamentos', 'catalogs.incident_types': 'Tipos de incidencia', 'catalogs.escalation_reasons': 'Motivos de escalamiento', 'catalogs.service_types': 'Tipos de servicio', 'catalogs.deactivation_reasons': 'Motivos de baja', 'catalogs.cpe_models': 'Modelos de CPE', 'catalogs.internal_incident_types': 'Tipos de incidencia interna', 'catalogs.providers': 'Proveedores', 'catalogs.change_completion_types': 'Tipos de finalización', 'catalogs.change_types': 'Tipos de cambio', 'catalogs.port_nomenclatures': 'Nomenclaturas de puertos', 'catalogs.distribution_device_templates': 'Plantillas de equipos', 'settings.ticket_number': 'Numeración de tickets', 'settings.internal_ticket_number': 'Numeración de tickets internos', 'settings.activation_number': 'Numeración de activaciones', 'settings.change_number': 'Numeración de cambios' }
  const parts = module.split('.')
  return labels[module] ?? (parts[0] === 'reports' ? 'Reportería · ' + (labels[parts[1]] ?? parts[1]) : parts[0] === 'mail' ? 'Correo · ' + ({ transport: 'Transporte SMTP', oauth: 'OAuth2', events: 'Eventos', templates: 'Plantillas', processor: 'Procesador' }[parts[1]] ?? parts[1]) : module.replaceAll('_', ' ').replace('catalogs.', 'Catálogo · ').replace('settings.', 'Configuración · ').replace('context.', 'Creación contextual · '))
}
