import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { createTicket, updateTicket, getTicketCatalogs, listCircuits, listCustomers, listDepartments, listIncidentTypes, listSectors } from '../api'
import type { Circuit, Customer, Department, IncidentType, Sector } from '../types/catalog'
import type { Ticket, TicketStatus } from '../types/ticket'
import { localDateTimeToIso, localDateTimeValue } from '../lib/datetime'
import { FormField } from '../components/FormField'
import { QuickCatalogCreate } from './QuickCatalogCreate'
import { SearchableSelect } from './SearchableSelect'
import { PageHeading } from '../components/PageHeading'

interface Catalogs {
  customers: Customer[]; sectors: Sector[]; departments: Department[]; incidentTypes: IncidentType[]
}

const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Ocurrió un error inesperado.'

export function TicketForm({ ticket }: { ticket?: Ticket }) {
  const navigate = useNavigate()
  const [title, setTitle] = useState(ticket?.title ?? '')
  const [description, setDescription] = useState(ticket?.description ?? '')
  const [customerId, setCustomerId] = useState(ticket ? String(ticket.customer_id) : '')
  const [circuitId, setCircuitId] = useState(ticket ? String(ticket.circuit_id) : '')
  const [sectorId, setSectorId] = useState(ticket ? String(ticket.sector_id) : '')
  const [departmentId, setDepartmentId] = useState(ticket ? String(ticket.department_id) : '')
  const [incidentTypeId, setIncidentTypeId] = useState(ticket ? String(ticket.incident_type_id) : '')
  const [startAt, setStartAt] = useState(() => localDateTimeValue(ticket ? new Date(ticket.start_at) : undefined))
  const [endAt, setEndAt] = useState(ticket?.end_at ? localDateTimeValue(new Date(ticket.end_at)) : '')
  const [status, setStatus] = useState<TicketStatus>(ticket?.status ?? 'OPEN')
  const [catalogs, setCatalogs] = useState<Catalogs | null>(null)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [catalogRetry, setCatalogRetry] = useState(0)
  const [circuits, setCircuits] = useState<Circuit[]>([])
  const [circuitLoading, setCircuitLoading] = useState(Boolean(ticket))
  const [circuitError, setCircuitError] = useState<string | null>(null)
  const [circuitRetry, setCircuitRetry] = useState(0)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [historical, setHistorical] = useState<Awaited<ReturnType<typeof getTicketCatalogs>> | null>(null)
  const [quickCreate, setQuickCreate] = useState<'customer' | 'circuit' | null>(null)
  const [quickNotice, setQuickNotice] = useState<string | null>(null)
  const selectedCustomer = catalogs?.customers.find((item) => String(item.id) === customerId)
  const sending = useRef(false)
  const submitController = useRef<AbortController | null>(null)

  useEffect(() => () => submitController.current?.abort(), [])
  useEffect(() => {
    const controller = new AbortController()
    setCatalogLoading(true)
    setCircuitLoading(Boolean(customerId))
    setCatalogError(null)
    Promise.all([
      listCustomers(controller.signal), listSectors(controller.signal),
      listDepartments(controller.signal), listIncidentTypes(controller.signal),
      ticket ? getTicketCatalogs(ticket, controller.signal) : Promise.resolve(null),
    ]).then(([customers, sectors, departments, incidentTypes, history]) => {
      if (!controller.signal.aborted) {
        const merge = <T extends { id: number }>(items: T[], current?: T): T[] => current && !items.some((item) => item.id === current.id) ? [...items, current] : items
        setHistorical(history)
        setCatalogs({ customers: merge(customers, history?.customer), sectors: merge(sectors, history?.sector), departments: merge(departments, history?.department), incidentTypes: merge(incidentTypes, history?.incidentType) })
        setCatalogLoading(false)
      }
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) {
        setCatalogError(errorMessage(error))
        setCatalogLoading(false)
      }
    })
    return () => controller.abort()
  }, [catalogRetry])

  useEffect(() => {
    if (!customerId || catalogLoading || catalogError) return
    const controller = new AbortController()
    setCircuitLoading(true)
    setCircuitError(null)
    listCircuits(Number(customerId), controller.signal).then((items) => {
      if (!controller.signal.aborted) { setCircuits(historical && historical.circuit.customer_id === Number(customerId) && !items.some((item) => item.id === historical.circuit.id) ? [...items, historical.circuit] : items); setCircuitLoading(false) }
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) { setCircuitError(errorMessage(error)); setCircuitLoading(false) }
    })
    return () => controller.abort()
  }, [customerId, circuitRetry, historical, catalogLoading, catalogError])

  function changeCustomer(value: string) {
    if (value === customerId) return
    setCustomerId(value)
    setCircuitId('')
    setCircuits([])
    setCircuitError(null)
    setCircuitLoading(Boolean(value))
  }

  function customerCreated(customer: Customer) {
    setCatalogs((current) => current ? { ...current, customers: [...current.customers.filter((item) => item.id !== customer.id), customer] } : current)
    changeCustomer(String(customer.id))
    setQuickCreate(null)
    setQuickNotice(`Cliente ${customer.customer_code} creado y seleccionado.`)
  }

  function circuitCreated(circuit: Circuit) {
    setCircuits((current) => [...current.filter((item) => item.id !== circuit.id), circuit])
    setCircuitId(String(circuit.id))
    setQuickCreate(null)
    setQuickNotice(`Circuito ${circuit.circuit_code} creado y seleccionado.`)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (sending.current) return
    setSubmitError(null)
    if (catalogLoading || catalogError || circuitLoading || circuitError) {
      setSubmitError('Espera a que se carguen los catálogos o reintenta su carga.')
      return
    }
    if (!title.trim() || !description.trim() || !customerId || !circuitId || !sectorId || !departmentId || !incidentTypeId || !startAt) {
      setSubmitError('Completa los campos obligatorios antes de guardar.')
      return
    }
    try {
      const start = ticket && startAt === localDateTimeValue(new Date(ticket.start_at)) ? ticket.start_at : localDateTimeToIso(startAt)
      const end = endAt ? (ticket?.end_at && endAt === localDateTimeValue(new Date(ticket.end_at)) ? ticket.end_at : localDateTimeToIso(endAt)) : null
      if (end && new Date(end).getTime() < new Date(start).getTime()) {
        setSubmitError('Fin debe ser igual o posterior a Inicio.')
        return
      }
      sending.current = true
      setSubmitting(true)
      const controller = new AbortController()
      submitController.current = controller
      const payload = {
        title: title.trim(), description: description.trim(), customer_id: Number(customerId),
        circuit_id: Number(circuitId), sector_id: Number(sectorId), department_id: Number(departmentId),
        incident_type_id: Number(incidentTypeId), start_at: start, end_at: end, status,
      }
      const created = ticket ? await updateTicket(ticket.id, payload, controller.signal) : await createTicket(payload, controller.signal)
      if (!controller.signal.aborted) navigate(ticket ? `/tickets/${ticket.id}` : '/tickets', { state: ticket ? { saved: true } : { createdReference: created.reference } })
    } catch (error) {
      if (!submitController.current?.signal.aborted) setSubmitError(errorMessage(error))
    } finally {
      sending.current = false
      if (!submitController.current?.signal.aborted) setSubmitting(false)
    }
  }

  return <>
    <PageHeading title={ticket ? `Editar ${ticket.reference}` : "Nuevo ticket"} description={ticket ? "Actualiza los datos operativos del ticket." : "Registra una incidencia. La referencia se asignará automáticamente al guardar."} />
    {quickNotice && <p role="status" className="mb-4 rounded-md bg-emerald-50 p-3 text-sm text-emerald-900">{quickNotice}</p>}
    {catalogLoading && <p role="status" className="mb-3 text-sm text-slate-500">Cargando catálogos...</p>}
    {catalogError && <div role="alert" className="panel mb-3 p-4"><p className="font-medium">Error al cargar catálogos</p><p className="mt-1 text-sm">{catalogError}</p><button type="button" className="button-secondary mt-3" onClick={() => setCatalogRetry(catalogRetry + 1)}>Reintentar catálogos</button></div>}
    <form onSubmit={submit} noValidate className="panel p-4 sm:p-5" aria-label={ticket ? "Editar ticket" : "Crear ticket"} aria-busy={submitting}>
      <fieldset disabled={submitting} className="min-w-0 space-y-5">
        <legend className="sr-only">Datos del ticket</legend>
        <section aria-labelledby="incident-heading" className="space-y-3">
          <h2 id="incident-heading" className="font-semibold text-slate-900">Incidencia</h2>
          <FormField id="title" label="Título" required><input id="title" className="form-input" required value={title} onChange={(e) => setTitle(e.target.value)} /></FormField>
          <FormField id="description" label="Descripción" required><textarea id="description" className="form-input resize-y" rows={3} required value={description} onChange={(e) => setDescription(e.target.value)} /></FormField>
        </section>
        <section aria-labelledby="relations-heading" className="border-t border-slate-200 pt-4">
          <h2 id="relations-heading" className="mb-3 text-sm font-semibold text-slate-900">Cliente y clasificación</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField id="customer" label="Cliente" required><div className="flex items-start gap-2"><div className="min-w-0 flex-1"><SearchableSelect id="customer" label="Cliente" required disabled={submitting || catalogLoading || Boolean(catalogError)} value={customerId} onChange={changeCustomer}
              options={(catalogs?.customers ?? []).map((item) => ({ value: String(item.id), label: `${item.customer_code} — ${item.name}`, disabled: !item.active }))}
              placeholder="Selecciona un cliente" emptyMessage="No se encontraron clientes." noMatchMessage="No se encontraron clientes." /></div><button type="button" className="button-secondary shrink-0" aria-label="Nuevo cliente" title="Nuevo cliente" disabled={submitting || catalogLoading || Boolean(catalogError)} onClick={() => setQuickCreate('customer')}>+</button></div></FormField>
            <FormField id="circuit" label="Circuito" required><div className="flex items-start gap-2"><div className="min-w-0 flex-1"><SearchableSelect id="circuit" label="Circuito" required disabled={submitting || !customerId || circuitLoading || Boolean(circuitError)} value={circuitId} onChange={setCircuitId}
              options={circuits.map((item) => ({ value: String(item.id), label: `${item.circuit_code} — ${item.description}`, disabled: !item.active }))}
              placeholder={!customerId ? 'Selecciona primero un cliente.' : circuitLoading ? 'Cargando circuitos...' : 'Selecciona un circuito'} emptyMessage="Este cliente no tiene circuitos activos." noMatchMessage="No se encontraron circuitos." /></div><button type="button" className="button-secondary shrink-0" aria-label="Nuevo circuito" title="Nuevo circuito" disabled={submitting || !selectedCustomer || catalogLoading || Boolean(catalogError) || circuitLoading || Boolean(circuitError)} onClick={() => setQuickCreate('circuit')}>+</button></div>
              {customerId && !circuitLoading && !circuitError && !circuits.some((item) => item.active) && !circuitId && <p className="mt-2 text-xs text-slate-600">Este cliente no tiene circuitos activos.</p>}
              {circuitError && <div role="alert" className="mt-2 text-sm text-red-700"><p>Error al cargar circuitos: {circuitError}</p><button type="button" className="button-secondary mt-2" onClick={() => setCircuitRetry(circuitRetry + 1)}>Reintentar circuitos</button></div>}
            </FormField>
            <FormField id="sector" label="Sector" required><select id="sector" className="form-input" required disabled={catalogLoading || Boolean(catalogError)} value={sectorId} onChange={(e) => setSectorId(e.target.value)}><option value="">Selecciona un sector</option>{catalogs?.sectors.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></FormField>
            <FormField id="department" label="Departamento" required><select id="department" className="form-input" required disabled={catalogLoading || Boolean(catalogError)} value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}><option value="">Selecciona un departamento</option>{catalogs?.departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></FormField>
            <FormField id="incident-type" label="Tipo de incidencia" required><select id="incident-type" className="form-input" required disabled={catalogLoading || Boolean(catalogError)} value={incidentTypeId} onChange={(e) => setIncidentTypeId(e.target.value)}><option value="">Selecciona un tipo de incidencia</option>{catalogs?.incidentTypes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></FormField>
            <FormField id="status" label="Estado" required><select id="status" className="form-input" value={status} onChange={(e) => setStatus(e.target.value === 'CLOSED' ? 'CLOSED' : 'OPEN')}><option value="OPEN">Abierto</option><option value="CLOSED">Cerrado</option></select></FormField>
          </div>
        </section>
        <section aria-labelledby="dates-heading" className="border-t border-slate-200 pt-4">
          {ticket && <button type="button" className="button-secondary mb-4" onClick={() => { setEndAt(localDateTimeValue()); setStatus('CLOSED') }}>Finalizar ahora</button>}
          <h2 id="dates-heading" className="mb-1 text-sm font-semibold text-slate-900">Tiempos operativos</h2>
          <p className="mb-3 text-xs text-slate-500">Fechas y horas de tu navegador. Puedes registrar una incidencia anterior; “Ahora” es solo un atajo.</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField id="start-at" label="Inicio" required><div className="flex items-center gap-2"><input id="start-at" type="datetime-local" step="60" className="form-input min-w-0" required value={startAt} onChange={(e) => setStartAt(e.target.value)} /><button type="button" className="button-secondary shrink-0" aria-label="Ahora de Inicio" onClick={() => setStartAt(localDateTimeValue())}>Ahora</button></div></FormField>
            <FormField id="end-at" label="Fin"><div className="flex items-center gap-2"><input id="end-at" type="datetime-local" step="60" className="form-input min-w-0" value={endAt} onChange={(e) => setEndAt(e.target.value)} /><button type="button" className="button-secondary shrink-0" aria-label="Ahora de Fin" onClick={() => setEndAt(localDateTimeValue())}>Ahora</button></div></FormField>
          </div>
        </section>
      </fieldset>
      {submitError && <p role="alert" className="mt-5 rounded-lg bg-red-50 p-3 text-sm text-red-800">{submitError}</p>}
      <div className="mt-5 flex justify-end gap-3 border-t border-slate-200 pt-4">
        <button type="button" className="button-secondary" disabled={submitting} onClick={() => navigate(ticket ? `/tickets/${ticket.id}` : '/tickets')}>Cancelar</button>
        <button type="submit" className="button-primary" disabled={submitting || catalogLoading || Boolean(catalogError) || circuitLoading || Boolean(circuitError)}>{submitting ? (ticket ? 'Guardando...' : 'Creando...') : (ticket ? 'Guardar cambios' : 'Guardar')}</button>
      </div>
    </form>
    {quickCreate === 'customer' && <QuickCatalogCreate kind="customer" onCancel={() => setQuickCreate(null)} onCreated={customerCreated} />}
    {quickCreate === 'circuit' && selectedCustomer && <QuickCatalogCreate kind="circuit" customer={selectedCustomer} onCancel={() => setQuickCreate(null)} onCreated={circuitCreated} />}
  </>
}
