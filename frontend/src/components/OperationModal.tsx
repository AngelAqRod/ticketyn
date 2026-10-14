import { circuitLabel } from '../lib/circuitLabel'
import { CircuitAssignmentField } from './CircuitAssignmentField'
import { CircuitSectorField } from './CircuitSectorField'
import { capacityInMicroMbps } from '../lib/capacity'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { listCircuits, listCustomers, listResponsibles, listDeactivationReasons, listSectors, listNodes } from '../api'
import { createOperation, getCircuitDetail } from '../api/fms'
import type { Circuit, Customer, NamedCatalog } from '../types/catalog'
import type { FmsKind } from '../types/fms'
import { fmsTitles } from '../types/fms'
import { ticketynDateTimeValue, ticketynDateTimeToIso } from '../lib/datetime'
import { SearchableSelect } from './SearchableSelect'
import { FormField } from './FormField'
import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'
import { CapacityFields } from './CapacityFields'
import { QuickCatalogCreate } from './QuickCatalogCreate'

export function OperationModal({ kind, circuit, onCancel, onSaved }: { kind: FmsKind; circuit?: Circuit; onCancel: () => void; onSaved: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null), sending = useRef(false)
  const [circuits, setCircuits] = useState<Circuit[]>([]), [customers, setCustomers] = useState<Customer[]>([]), [people, setPeople] = useState<NamedCatalog[]>([]), [reasons, setReasons] = useState<NamedCatalog[]>([])
  const [circuitId, setCircuitId] = useState(circuit ? String(circuit.id) : ''), [customerId, setCustomerId] = useState(circuit ? String(circuit.customer_id) : ''), [responsibleId, setResponsibleId] = useState(''), [reasonId, setReasonId] = useState('')
  const [effective, setEffective] = useState(ticketynDateTimeValue), [type, setType] = useState(kind === 'capacity-changes' ? 'INCREASE' : 'DEACTIVATE')
  const [previous, setPrevious] = useState(''), [previousUnit, setPreviousUnit] = useState('Mbps'), [next, setNext] = useState(''), [nextUnit, setNextUnit] = useState('Mbps'), [description, setDescription] = useState('')
  const [loading, setLoading] = useState(true), [saving, setSaving] = useState(false), [error, setError] = useState<string | null>(null), [retry, setRetry] = useState(0)
  const capacityTouched = useRef(false), capacityCircuit = useRef(circuitId)
  const [capacityLoading, setCapacityLoading] = useState(false), [capacityError, setCapacityError] = useState<string | null>(null), [capacityRetry, setCapacityRetry] = useState(0)
  const [circuitLoading, setCircuitLoading] = useState(false), [circuitError, setCircuitError] = useState<string | null>(null), [circuitRetry, setCircuitRetry] = useState(0)
  const [nodes, setNodes] = useState<NamedCatalog[]>([]), [nodeId, setNodeId] = useState('')
  const [sectors, setSectors] = useState<NamedCatalog[]>([]), [sectorId, setSectorId] = useState('')
  const selectedCircuit = circuits.find(item => String(item.id) === circuitId) ?? (circuit && String(circuit.id) === circuitId ? circuit : undefined)
  const [quick, setQuick] = useState<'customer' | 'circuit' | null>(null)
  useEffect(() => { const element = dialog.current!, focus = document.activeElement; element.showModal(); element.querySelector<HTMLElement>('button, input')?.focus(); return () => { element.close(); if (focus instanceof HTMLElement && focus.isConnected) focus.focus() } }, [])
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null)
    Promise.all([listCustomers(controller.signal, true), listResponsibles(controller.signal), kind === 'circuit-lifecycle' ? listDeactivationReasons(controller.signal) : Promise.resolve([]), listSectors(controller.signal), listNodes(controller.signal)]).then(([clients, p, r, s, n]) => {
      if (!controller.signal.aborted) { setCustomers((old) => [...clients, ...old.filter((item) => !clients.some((row) => row.id === item.id))]); setPeople(p); setReasons(r); setSectors(s); setNodes(n); setLoading(false) }
    }).catch((failure: unknown) => { if (!controller.signal.aborted) { setError(failure instanceof Error ? failure.message : 'No se pudieron cargar los catálogos.'); setLoading(false) } })
    return () => controller.abort()
  }, [kind, retry])
  useEffect(() => {
    if (circuit) return
    const request = new AbortController()
    if (!customerId) { setCircuits([]); setCircuitLoading(false); setCircuitError(null); return }
    setCircuitLoading(true); setCircuitError(null)
    listCircuits(Number(customerId), request.signal, true).then((rows) => {
      if (!request.signal.aborted) {
        setCircuits((old) => [...rows, ...old.filter((item) => String(item.customer_id) === customerId && !rows.some((row) => row.id === item.id))])
        setCircuitLoading(false)
      }
    }).catch((failure: unknown) => { if (!request.signal.aborted) { setCircuitLoading(false); setCircuitError(failure instanceof Error ? failure.message : 'No se pudieron cargar los circuitos del cliente.') } })
    return () => request.abort()
  }, [kind, circuit, customerId, circuitRetry])
  function chooseCircuit(value: string) {
    if (value === capacityCircuit.current) return
    capacityCircuit.current = value; capacityTouched.current = false
    setSectorId(''); setNodeId(''); setCircuitId(value); setPrevious(''); setPreviousUnit('Mbps'); setCapacityError(null)
  }
  function chooseCustomer(value: string) {
    if (value === customerId) return
    chooseCircuit(''); setCircuits([]); setCircuitLoading(Boolean(value)); setCircuitError(null)
    setPrevious(''); setPreviousUnit('Mbps'); capacityTouched.current = false
    setCustomerId(value)
  }
  useEffect(() => {
    if (kind !== 'capacity-changes' || !circuitId) { setCapacityLoading(false); return }
    const request = new AbortController(), selected = circuitId
    setCapacityLoading(true); setCapacityError(null)
    getCircuitDetail(Number(selected), request.signal).then((data) => {
      if (request.signal.aborted || capacityCircuit.current !== selected) return
      if (!capacityTouched.current && !sending.current) {
        setPrevious(data.current_capacity ?? ''); setPreviousUnit(data.current_capacity_unit ?? 'Mbps')
      }
      setCapacityLoading(false)
    }).catch((failure: unknown) => {
      if (!request.signal.aborted && capacityCircuit.current === selected) { setCapacityLoading(false); setCapacityError(failure instanceof Error ? failure.message : 'No se pudo consultar la capacidad vigente.') }
    })
    return () => request.abort()
  }, [kind, circuitId, capacityRetry])
  async function submit(event: FormEvent) {
    event.preventDefault(); if (sending.current) return
    setError(null)
    try {
      if (loading || circuitLoading || circuitError) throw new Error('Espera a que se carguen los circuitos o reintenta su carga.')
      if (!customerId || !selectedCircuit || String(selectedCircuit.customer_id) !== customerId) throw new Error('El circuito debe pertenecer al cliente seleccionado.')
      if (!circuitId || !responsibleId) throw new Error('Selecciona circuito y responsable.')
      if (!selectedCircuit?.node_id && !nodeId) throw new Error('Selecciona un Nodo para el circuito antes de guardar.')
      if (!selectedCircuit?.sector_id && !sectorId) throw new Error('Selecciona un Sector para el circuito antes de guardar.')
      const payload: Record<string, unknown> = { circuit_id: Number(circuitId), responsible_id: Number(responsibleId), effective_at: ticketynDateTimeToIso(effective), ...(!selectedCircuit?.node_id ? { node_id: Number(nodeId) } : {}), ...(!selectedCircuit?.sector_id ? { sector_id: Number(sectorId) } : {}) }
      if (kind === 'activations') {
        const selected = circuit ?? circuits.find((item) => String(item.id) === circuitId)
        if (!customerId || !selected || String(selected.customer_id) !== customerId) throw new Error('El circuito debe pertenecer al cliente seleccionado.')
        payload.customer_id = Number(customerId)
      }
      if (kind === 'capacity-changes') {
        const current = capacityInMicroMbps(next, nextUnit)
        const old = previous ? capacityInMicroMbps(previous, previousUnit) : null
        if (type === 'DECREASE' && !previous) throw new Error('Un decremento requiere capacidad anterior conocida.')
        if (old !== null && ((type === 'INCREASE' && current <= old) || (type === 'DECREASE' && current >= old))) throw new Error('La nueva capacidad no corresponde al tipo de operación seleccionado.')
        Object.assign(payload, { operation_type: type, previous_capacity: previous || null, previous_unit: previous ? previousUnit : null, new_capacity: next, new_unit: nextUnit, description: description.trim() || null })
      }
      if (kind === 'circuit-lifecycle') {
        if (type === 'DEACTIVATE' && !reasonId) throw new Error('Selecciona un motivo de baja.')
        Object.assign(payload, { operation_type: type, reason_id: type === 'DEACTIVATE' ? Number(reasonId) : null, observations: description.trim() || null })
      }
      sending.current = true; setSaving(true)
      await createOperation(kind, payload); onSaved()
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'No se pudo registrar la operación.') }
    finally { sending.current = false; setSaving(false) }
  }
  const client = customers.find((item) => String(item.id) === customerId)
  const availableCircuits = [...circuits, ...(circuit && !circuits.some((item) => item.id === circuit.id) ? [circuit] : [])].filter((item) => customerId && String(item.customer_id) === customerId)
  return <><dialog ref={dialog} className="quick-dialog fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-xl overflow-y-auto bg-white p-5 text-ink backdrop:bg-slate-900/30" aria-labelledby="operation-title" onCancel={(event) => { event.preventDefault(); if (!sending.current && !quick) onCancel() }}>
    <h2 id="operation-title" className="mb-4 text-xl font-semibold">Registrar · {fmsTitles[kind]}</h2>
    <RequestState loading={loading} compact error={loading ? null : people.length ? null : error} onRetry={() => setRetry(retry + 1)} />
    <form aria-label="Registrar operación" onSubmit={submit} aria-describedby={error ? 'operation-error' : undefined}>
      <fieldset disabled={saving || loading || !people.length} className="space-y-3"><legend className="sr-only">Datos operativos</legend>
        {(!circuit || kind !== 'activations') && <FormField id="operation-client" label="Cliente" required><div className="flex flex-wrap gap-2"><div className="min-w-0 flex-1"><SearchableSelect placeholder="Selecciona un cliente" emptyMessage="No hay clientes disponibles." noMatchMessage="Sin coincidencias." required id="operation-client" label="Cliente" disabled={Boolean(circuit)} value={customerId} onChange={chooseCustomer} options={customers.map((item) => ({ value: String(item.id), label: `${item.customer_code} — ${item.name}${item.active ? '' : ' (Inactivo)'}` }))} /></div>{kind === 'activations' && <button type="button" className="button-secondary" onClick={() => setQuick('customer')}>Nuevo cliente</button>}</div></FormField>}
        <FormField id="operation-circuit" label="Circuito" required><div className="flex flex-wrap gap-2"><div className="min-w-0 flex-1"><SearchableSelect placeholder={!customerId ? 'Selecciona un cliente primero' : 'Selecciona un circuito'} emptyMessage="Este cliente no tiene circuitos registrados." noMatchMessage="Sin coincidencias." required id="operation-circuit" label="Circuito" value={circuitId} onChange={chooseCircuit} disabled={Boolean(circuit) || (!customerId || circuitLoading || Boolean(circuitError))} options={availableCircuits.map((item) => ({ value: String(item.id), label: circuitLabel(item) }))} /></div>{kind === 'activations' && !circuit && <button type="button" className="button-secondary" disabled={!client} onClick={() => setQuick('circuit')}>Nuevo circuito</button>}</div>{<RequestState compact loading={circuitLoading} loadingText="Cargando circuitos del cliente..." errorTitle="" error={circuitError} retryText="Reintentar circuitos" onRetry={() => setCircuitRetry(circuitRetry + 1)} />}</FormField>
        <CircuitAssignmentField field="node" id="operation-node" circuit={selectedCircuit} options={nodes} value={nodeId} onChange={setNodeId} disabled={loading || saving} />
        <CircuitSectorField id="operation-sector" circuit={selectedCircuit} sectors={sectors} value={sectorId} onChange={setSectorId} disabled={loading || saving} />
        {kind !== 'activations' && <FormField id="operation-type" label="Tipo de operación"><select id="operation-type" className="form-input" value={type} onChange={(event) => setType(event.target.value)}>{kind === 'capacity-changes' ? <><option value="INCREASE">Incremento</option><option value="DECREASE">Decremento</option></> : <><option value="DEACTIVATE">Baja</option><option value="REACTIVATE">Reactivación</option></>}</select></FormField>}
        <FormField id="operation-effective" label="Fecha y hora efectiva" required><input id="operation-effective" type="datetime-local" className="form-input" required value={effective} onChange={(event) => setEffective(event.target.value)} /></FormField>
        <FormField id="operation-responsible" label="Responsable" required><SearchableSelect placeholder="Selecciona una opción" emptyMessage="No hay registros disponibles." noMatchMessage="Sin coincidencias." required id="operation-responsible" label="Responsable" value={responsibleId} onChange={setResponsibleId} options={people.map((item) => ({ value: String(item.id), label: item.name }))} /></FormField>
        {kind === 'capacity-changes' && <><RequestState compact errorTitle="" loading={capacityLoading} loadingText="Consultando capacidad vigente..." error={capacityError} retryText="Reintentar capacidad" onRetry={() => setCapacityRetry(capacityRetry + 1)} /><CapacityFields id="operation-previous" label={type === 'DECREASE' ? 'Capacidad anterior' : 'Capacidad anterior (opcional)'} required={type === 'DECREASE'} value={previous} unit={previousUnit} onChange={(v, u) => { capacityTouched.current = true; setPrevious(v); setPreviousUnit(u) }} /><CapacityFields id="operation-new" label="Capacidad nueva" required value={next} unit={nextUnit} onChange={(v, u) => { setNext(v); setNextUnit(u) }} /></>}
        {kind === 'circuit-lifecycle' && type === 'DEACTIVATE' && <FormField id="operation-reason" label="Motivo de baja" required><SearchableSelect placeholder="Selecciona una opción" emptyMessage="No hay registros disponibles." noMatchMessage="Sin coincidencias." required id="operation-reason" label="Motivo de baja" value={reasonId} onChange={setReasonId} options={reasons.map((item) => ({ value: String(item.id), label: item.name }))} /></FormField>}
        {kind !== 'activations' && <FormField id="operation-description" label={kind === 'capacity-changes' ? 'Descripción (opcional)' : 'Observaciones (opcional)'}><textarea id="operation-description" className="form-input" maxLength={10000} value={description} onChange={(event) => setDescription(event.target.value)} /></FormField>}
      </fieldset>
      {error && <FeedbackMessage id="operation-error" variant="error" className="mt-3">{error}</FeedbackMessage>}
      <div className="mt-4 flex justify-end gap-2"><button type="button" className="button-secondary" disabled={saving} onClick={onCancel}>Cancelar</button><button type="submit" className="button-primary" disabled={saving || loading || !people.length || circuitLoading || Boolean(circuitError) || (capacityLoading && !capacityTouched.current)}>{saving ? 'Guardando...' : 'Registrar'}</button></div>
    </form>
  </dialog>
    {quick === 'customer' && <QuickCatalogCreate kind="customer" onCancel={() => setQuick(null)} onCreated={(item) => { setCustomers((old) => [...old, item]); chooseCustomer(String(item.id)); setQuick(null) }} />}
    {quick === 'circuit' && client && <QuickCatalogCreate kind="circuit" customer={client} onCancel={() => setQuick(null)} onCreated={(item) => { setCircuits((old) => [...old, item]); chooseCircuit(String(item.id)); setQuick(null) }} />}
  </>
}
