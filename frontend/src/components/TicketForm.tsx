import { operationalChoice } from '../lib/responsibles'
import { Can, usePermissions } from '../auth/permissions'
import { Check, Clock, FileText, Link2, Pencil, Tag, Ticket as TicketIcon, Users } from 'lucide-react'
import { InternalTicketSelect } from './InternalTicketSelect'
import { circuitLabel } from '../lib/circuitLabel'
import { CircuitAssignmentField } from './CircuitAssignmentField'
import { CircuitSectorField } from './CircuitSectorField'
import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'
import { ApiError } from '../api/client'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { createTicket, updateTicket, getTicketCatalogs, listCircuits, listCustomers, listDepartments, listIncidentTypes, listSectors, listResponsibles, listNodes } from '../api'
import type { Circuit, Customer, Department, IncidentType, Sector, Responsible } from '../types/catalog'
import type { Ticket, TicketStatus } from '../types/ticket'
import { localDateTimeToIso, localDateTimeValue } from '../lib/datetime'
import { FormField } from '../components/FormField'
import { QuickCatalogCreate } from './QuickCatalogCreate'
import { SearchableSelect } from './SearchableSelect'
import { StatusBadge } from './StatusBadge'

interface Catalogs {
  nodes: Pick<Sector, 'id' | 'name' | 'active'>[]; responsibles: Responsible[]; customers: Customer[]; sectors: Sector[]; departments: Department[]; incidentTypes: IncidentType[]
}

const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'Ocurrió un error inesperado.'

export function TicketForm({ ticket }: { ticket?: Ticket }) {
  const access=usePermissions(), editable=!ticket||access.can("tickets.edit"), mayResolve=editable||access.can("tickets.close")
  const navigate = useNavigate()
  const [internalTicketId, setInternalTicketId] = useState(ticket?.internal_ticket_id ? String(ticket.internal_ticket_id) : '')
  const [title, setTitle] = useState(ticket?.title ?? '')
  const [description, setDescription] = useState(ticket?.description ?? '')
  const [resolution, setResolution] = useState(ticket?.resolution ?? '')
  const [customerDescription, setCustomerDescription] = useState(ticket?.customer_description ?? '')
  const [customerResolution, setCustomerResolution] = useState(ticket?.customer_resolution ?? '')
  const [customerId, setCustomerId] = useState(ticket ? String(ticket.customer_id) : '')
  const [circuitId, setCircuitId] = useState(ticket ? String(ticket.circuit_id) : '')
  const [responsibleId, setResponsibleId] = useState(ticket?.responsible_id ? String(ticket.responsible_id) : '')
  const [nodeId, setNodeId] = useState('')
  const [sectorId, setSectorId] = useState('')
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
  const [apiInvalidFields, setApiInvalidFields] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [historical, setHistorical] = useState<Awaited<ReturnType<typeof getTicketCatalogs>> | null>(null)
  const [quickCreate, setQuickCreate] = useState<'customer' | 'circuit' | null>(null)
  const [quickNotice, setQuickNotice] = useState<string | null>(null)
  const selectedCircuit = circuits.find(item => String(item.id) === circuitId)
  const effectiveNodeId = selectedCircuit?.node_id ? String(selectedCircuit.node_id) : nodeId
  const effectiveSectorId = selectedCircuit?.sector_id ? String(selectedCircuit.sector_id) : sectorId
  function chooseCircuit(value: string) { if (value !== circuitId) { setSectorId(''); setNodeId('') }; setCircuitId(value) }
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
      listResponsibles(controller.signal), listNodes(controller.signal),
      ticket ? getTicketCatalogs(ticket, controller.signal) : Promise.resolve(null),
    ]).then(([customers, sectors, departments, incidentTypes, responsibles, nodes, history]) => {
      if (!controller.signal.aborted) {
        const merge = <T extends { id: number }>(items: T[], current?: T): T[] => current && !items.some((item) => item.id === current.id) ? [...items, current] : items
        setHistorical(history)
        setCatalogs({ nodes: merge(nodes, history?.node ?? undefined), responsibles: merge(responsibles, history?.responsible ?? undefined), customers: merge(customers, history?.customer), sectors: merge(sectors, history?.sector), departments: merge(departments, history?.department), incidentTypes: merge(incidentTypes, history?.incidentType) })
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
    chooseCircuit('')
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
    chooseCircuit(String(circuit.id))
    setQuickCreate(null)
    setQuickNotice(`Circuito ${circuit.circuit_code} creado y seleccionado.`)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (sending.current) return
    setSubmitError(null); setApiInvalidFields([])
    if (catalogLoading || catalogError || circuitLoading || circuitError) {
      setSubmitError('Espera a que se carguen los catálogos o reintenta su carga.')
      return
    }
    if (!title.trim() || !description.trim() || !customerId || !circuitId || !effectiveSectorId || !effectiveNodeId || !departmentId || !incidentTypeId || !startAt) {
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
      const optionalTexts = { resolution: resolution.trim() ? resolution : null, customer_description: customerDescription.trim() ? customerDescription : null, customer_resolution: customerResolution.trim() ? customerResolution : null }
      const changedTexts = Object.fromEntries(Object.entries(optionalTexts).filter(([field, value]) =>
        ticket ? value !== (ticket[field as keyof typeof optionalTexts] ?? null) : value !== null))
      const payload = {
        ...changedTexts,
        ...((internalTicketId || ticket?.internal_ticket_id) ? { internal_ticket_id: internalTicketId ? Number(internalTicketId) : null } : {}),
        title: title.trim(), description: description.trim(), customer_id: Number(customerId),
        circuit_id: Number(circuitId), ...(!ticket || ticket.circuit_id !== Number(circuitId) || !selectedCircuit?.node_id ? { node_id: Number(effectiveNodeId) } : {}), ...(ticket && ticket.circuit_id === Number(circuitId) && selectedCircuit?.sector_id ? {} : { sector_id: Number(effectiveSectorId) }), department_id: Number(departmentId),
        responsible_id: responsibleId ? Number(responsibleId) : null, incident_type_id: Number(incidentTypeId), start_at: start, end_at: end, status,
      }
      const created = ticket ? await updateTicket(ticket.id, payload, controller.signal) : await createTicket(payload, controller.signal)
      if (!controller.signal.aborted) navigate(ticket ? `/tickets/${ticket.id}` : '/tickets', { state: ticket ? { saved: true } : { createdReference: created.reference } })
    } catch (error) {
      if (!submitController.current?.signal.aborted) { setSubmitError(errorMessage(error)); setApiInvalidFields(error instanceof ApiError ? error.fields : []) }
    } finally {
      sending.current = false
      if (!submitController.current?.signal.aborted) setSubmitting(false)
    }
  }

  return <>
    {/* 1. CABECERA INDUSTRIAL DEL REGISTRO (RECORD HEADER) */}
    <div className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl flex flex-wrap items-center justify-between gap-4 mb-5">
      <div className="flex items-center gap-4 min-w-0">
        <div className="h-12 w-12 shrink-0 rounded-xl bg-gradient-to-br from-sky-500 to-blue-600 flex items-center justify-center text-white shadow-lg shadow-sky-500/20" aria-hidden="true">
          {ticket ? <Pencil size={24} /> : <TicketIcon size={24} />}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[11px] font-mono text-sky-400 font-bold uppercase tracking-wider">
            <span>OPERACIÓN</span>
            <span className="text-slate-600">/</span>
            <span>{ticket ? 'EDICIÓN DE TICKET' : 'NUEVO TICKET'}</span>
          </div>
          <div className="flex flex-wrap items-center gap-3 mt-0.5">
            <h1 className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-white">
              {ticket ? `Editar ${ticket.reference}` : 'Nuevo ticket'}
            </h1>
            {ticket ? (
              <>
                <StatusBadge status={status} />
                {selectedCircuit && (
                  <span className="hidden sm:inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full text-[11px] font-mono bg-slate-900 border border-slate-700 text-slate-300">
                    <span className="text-slate-500">CID:</span> <strong className="text-sky-300">{selectedCircuit.circuit_code}</strong>
                  </span>
                )}
              </>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full text-[11px] font-mono bg-sky-500/10 border border-sky-500/30 text-sky-300 font-bold">
                NUEVO REGISTRO
              </span>
            )}
          </div>
          {ticket ? (
            <p className="mt-1 text-sm font-semibold text-slate-300 truncate">{ticket.title}</p>
          ) : (
            <p className="mt-1 text-xs text-slate-400">
              Registra una incidencia técnica. La referencia correlativa se asignará automáticamente al guardar.
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Link to={ticket ? `/tickets/${ticket.id}` : '/tickets'} className="button-secondary rounded-full">
          {ticket ? 'Volver al detalle' : 'Volver a tickets'}
        </Link>
      </div>
    </div>

    {quickNotice && <FeedbackMessage variant="success" className="mb-4">{quickNotice}</FeedbackMessage>}
    {catalogLoading && <RequestState loading compact loadingText="Cargando catálogos..." className="mb-3" />}
    {catalogError && <RequestState compact error={catalogError} errorTitle="Error al cargar catálogos" retryText="Reintentar catálogos" onRetry={() => setCatalogRetry(catalogRetry + 1)} className="mb-3" />}

    <form onSubmit={submit} noValidate className="ticket-noc-form" aria-label={ticket ? "Editar ticket" : "Crear ticket"} aria-busy={submitting} aria-describedby={submitError ? "ticket-submit-error" : undefined}>
      <fieldset disabled={submitting} className="min-w-0">
        <legend className="sr-only">Datos del ticket</legend>

        <div className="grid gap-5 lg:grid-cols-3">
          {/* COLUMNA PRINCIPAL (2 COLS) */}
          <div className="lg:col-span-2 space-y-5">
            {/* INCIDENCIA */}
            <section aria-labelledby="incident-heading" className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs" aria-hidden="true"><FileText size={13} /></span>
                  <h2 id="incident-heading" className="text-xs font-bold font-mono text-white uppercase tracking-wider">Incidencia</h2>
                </div>
                <span className="text-[11px] font-mono text-slate-500">Datos primarios</span>
              </div>
              <FormField describedBy={submitError ? "ticket-submit-error" : undefined} invalid={(submitError === "Completa los campos obligatorios antes de guardar." && !title.trim()) || apiInvalidFields.includes("title")} id="title" label="Título" required>
                <input readOnly={!editable} id="title" className="form-input" required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ej. Corte de fibra en enlace troncal" />
              </FormField>
              <FormField describedBy={submitError ? "ticket-submit-error" : undefined} invalid={(submitError === "Completa los campos obligatorios antes de guardar." && !description.trim()) || apiInvalidFields.includes("description")} id="description" label="Descripción" required>
                <textarea readOnly={!editable} id="description" className="form-input resize-y" rows={4} required value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Detalle técnico de la falla o interrupción observada..." />
              </FormField>
            </section>

            {/* CLIENTE Y CLASIFICACIÓN */}
            <section aria-labelledby="relations-heading" className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs" aria-hidden="true"><Tag size={13} /></span>
                  <h2 id="relations-heading" className="text-xs font-bold font-mono text-white uppercase tracking-wider">Cliente y clasificación</h2>
                </div>
                <span className="text-[11px] font-mono text-slate-500">Relación operativa</span>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField describedBy={submitError ? "ticket-submit-error" : undefined} invalid={(submitError === "Completa los campos obligatorios antes de guardar." && !customerId.trim()) || apiInvalidFields.includes("customer_id")} id="customer" label="Cliente" required>
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <SearchableSelect id="customer" label="Cliente" required disabled={!editable || submitting || catalogLoading || Boolean(catalogError)} value={customerId} onChange={changeCustomer}
                        options={(catalogs?.customers ?? []).map((item) => ({ value: String(item.id), label: `${item.customer_code} — ${item.name}`, disabled: !item.active }))}
                        placeholder="Selecciona un cliente" emptyMessage="No se encontraron clientes." noMatchMessage="No se encontraron clientes." />
                    </div>
                    <Can anyOf={["customers.create","context.customers.create"]}>
                      <button type="button" className="button-secondary rounded-full shrink-0" aria-label="Nuevo cliente" title="Nuevo cliente" disabled={!editable || submitting || catalogLoading || Boolean(catalogError)} onClick={() => setQuickCreate('customer')}>+</button>
                    </Can>
                  </div>
                </FormField>
                <FormField describedBy={[submitError ? "ticket-submit-error" : "", circuitError ? "ticket-circuit-error" : ""].filter(Boolean).join(" ") || undefined} invalid={(submitError === "Completa los campos obligatorios antes de guardar." && !circuitId.trim()) || apiInvalidFields.includes("circuit_id")} id="circuit" label="Circuito" required>
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <SearchableSelect id="circuit" label="Circuito" required disabled={!editable || submitting || !customerId || circuitLoading || Boolean(circuitError)} value={circuitId} onChange={chooseCircuit}
                        options={circuits.map((item) => ({ value: String(item.id), label: circuitLabel(item), disabled: !item.active }))}
                        placeholder={!customerId ? 'Selecciona primero un cliente.' : circuitLoading ? 'Cargando circuitos...' : 'Selecciona un circuito'} emptyMessage="Este cliente no tiene circuitos activos." noMatchMessage="No se encontraron circuitos." />
                    </div>
                    <Can anyOf={["circuits.create","context.circuits.create"]}>
                      <button type="button" className="button-secondary rounded-full shrink-0" aria-label="Nuevo circuito" title="Nuevo circuito" disabled={!editable || submitting || !selectedCustomer || catalogLoading || Boolean(catalogError) || circuitLoading || Boolean(circuitError)} onClick={() => setQuickCreate('circuit')}>+</button>
                    </Can>
                  </div>
                  {customerId && !circuitLoading && !circuitError && !circuits.some((item) => item.active) && !circuitId && <p className="mt-2 text-xs text-amber-400">Este cliente no tiene circuitos activos.</p>}
                  {circuitError && <RequestState id="ticket-circuit-error" compact error={`Error al cargar circuitos: ${circuitError}`} errorTitle="" retryText="Reintentar circuitos" onRetry={() => setCircuitRetry(circuitRetry + 1)} className="mt-2" />}
                </FormField>
                <CircuitAssignmentField
                  field="node"
                  id="ticket-node"
                  circuit={selectedCircuit}
                  options={catalogs?.nodes ?? []}
                  value={nodeId}
                  onChange={setNodeId}
                  persistedName={ticket && String(ticket.circuit_id) === circuitId ? (ticket.node?.name ?? catalogs?.nodes.find(item => item.id === ticket.node_id)?.name) : undefined}
                  disabled={!editable || catalogLoading || Boolean(catalogError) || submitting}
                  describedBy={submitError ? "ticket-submit-error" : undefined}
                  invalid={Boolean(submitError && !effectiveNodeId) || apiInvalidFields.includes("node_id")}
                />
                <FormField describedBy={submitError ? "ticket-submit-error" : undefined} invalid={apiInvalidFields.includes("responsible_id")} id="responsible" label="Responsable">
                  <SearchableSelect id="responsible" label="Responsable" value={responsibleId} onChange={setResponsibleId} disabled={!editable || catalogLoading || Boolean(catalogError)} options={(catalogs?.responsibles ?? []).filter(p => operationalChoice(p, ticket?.responsible_id ? [ticket.responsible_id] : [])).map((item) => ({ value: String(item.id), label: item.name, disabled: !item.active }))} placeholder="Sin asignar" emptyMessage="No hay responsables activos." noMatchMessage="No se encontraron responsables." />
                </FormField>
                <CircuitSectorField
                  describedBy={submitError ? "ticket-submit-error" : undefined}
                  invalid={Boolean(submitError && !effectiveSectorId) || apiInvalidFields.includes("sector_id")}
                  id="sector"
                  circuit={selectedCircuit}
                  sectors={catalogs?.sectors ?? []}
                  value={sectorId}
                  onChange={setSectorId}
                  persistedName={ticket && String(ticket.circuit_id) === circuitId ? (historical?.sector?.name ?? catalogs?.sectors.find(item => item.id === ticket.sector_id)?.name) : undefined}
                  disabled={!editable || catalogLoading || Boolean(catalogError) || submitting}
                />
                <FormField describedBy={submitError ? "ticket-submit-error" : undefined} invalid={(submitError === "Completa los campos obligatorios antes de guardar." && !departmentId.trim()) || apiInvalidFields.includes("department_id")} id="department" label="Departamento" required>
                  <select id="department" className="form-input" required disabled={!editable || catalogLoading || Boolean(catalogError)} value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}>
                    <option value="">Selecciona un departamento</option>
                    {catalogs?.departments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </FormField>
                <FormField describedBy={submitError ? "ticket-submit-error" : undefined} invalid={(submitError === "Completa los campos obligatorios antes de guardar." && !incidentTypeId.trim()) || apiInvalidFields.includes("incident_type_id")} id="incident-type" label="Tipo de incidencia" required>
                  <select id="incident-type" className="form-input" required disabled={!editable || catalogLoading || Boolean(catalogError)} value={incidentTypeId} onChange={(e) => setIncidentTypeId(e.target.value)}>
                    <option value="">Selecciona un tipo de incidencia</option>
                    {catalogs?.incidentTypes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </FormField>
                <FormField describedBy={submitError ? "ticket-submit-error" : undefined} invalid={apiInvalidFields.includes("status")} id="status" label="Estado" required>
                  <select id="status" disabled={!access.can("tickets.close")} className="form-input" value={status} onChange={(e) => setStatus(e.target.value === 'CLOSED' ? 'CLOSED' : 'OPEN')}>
                    <option value="OPEN">Abierto</option>
                    <option value="CLOSED">Cerrado</option>
                  </select>
                </FormField>
              </div>
            </section>

            {/* RESOLUCIÓN DOCUMENTADA */}
            <section aria-labelledby="resolution-heading" className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-3">
              <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs" aria-hidden="true"><Check size={13} /></span>
                  <h2 id="resolution-heading" className="text-xs font-bold font-mono text-white uppercase tracking-wider">Resolución documentada</h2>
                </div>
                <span className="text-[11px] font-mono text-emerald-400/80">Cierre operativo</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed m-0">Opcional. Explica cómo se resolvió el incidente; puedes completarla o corregirla después del cierre. Los cambios quedan registrados como seguimiento interno, sin identificar al editor.</p>
              <FormField id="resolution" label="Resolución interna" describedBy={submitError ? 'ticket-submit-error' : undefined} invalid={apiInvalidFields.includes('resolution')}>
                <textarea readOnly={!mayResolve} id="resolution" className="form-input resize-y" rows={3} maxLength={10000} value={resolution} onChange={(event) => setResolution(event.target.value)} placeholder="Descripción técnica de la solución aplicada..." />
              </FormField>
            </section>

            {/* CONTENIDO AUTORIZADO PARA CLIENTE */}
            <section aria-labelledby="customer-report-heading" className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs" aria-hidden="true"><Users size={13} /></span>
                  <h2 id="customer-report-heading" className="text-xs font-bold font-mono text-white uppercase tracking-wider">Contenido autorizado para cliente</h2>
                </div>
                <span className="text-[11px] font-mono text-sky-400/80">Reportes externos</span>
              </div>
              <div className="p-3 rounded-xl bg-sky-950/40 border border-sky-500/25 text-xs text-sky-200 leading-relaxed flex items-start gap-2.5">
                <span className="text-sky-400 shrink-0 mt-0.5 font-bold font-mono">ℹ</span>
                <p id="customer-report-help" className="m-0">
                  Al guardar estos textos autorizas su inclusión en el PDF para cliente. Revisa que no contengan IP internas, comentarios privados ni información sensible. Nunca se copia automáticamente la descripción ni la resolución interna. Vaciar un campo retira ese texto del reporte.
                </p>
              </div>
              <FormField id="customer-description" label="Descripción del incidente" describedBy={['customer-report-help', submitError ? 'ticket-submit-error' : ''].filter(Boolean).join(' ')} invalid={apiInvalidFields.includes('customer_description')}>
                <textarea readOnly={!editable} id="customer-description" className="form-input resize-y" rows={3} maxLength={10000} value={customerDescription} onChange={(event) => setCustomerDescription(event.target.value)} placeholder="Descripción autorizada para el reporte formal al cliente..." />
              </FormField>
              <FormField id="customer-resolution" label="Resolución del incidente" describedBy={['customer-report-help', submitError ? 'ticket-submit-error' : ''].filter(Boolean).join(' ')} invalid={apiInvalidFields.includes('customer_resolution')}>
                <textarea readOnly={!editable} id="customer-resolution" className="form-input resize-y" rows={3} maxLength={10000} value={customerResolution} onChange={(event) => setCustomerResolution(event.target.value)} placeholder="Resolución autorizada para el reporte formal al cliente..." />
              </FormField>
            </section>
          </div>

          {/* COLUMNA LATERAL (1 COL) */}
          <div className="lg:col-span-1 space-y-5">
            {/* TIEMPOS OPERATIVOS */}
            <section aria-labelledby="dates-heading" className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs" aria-hidden="true"><Clock size={13} /></span>
                  <h2 id="dates-heading" className="text-xs font-bold font-mono text-white uppercase tracking-wider">Tiempos operativos</h2>
                </div>
                <span className="text-[11px] font-mono text-amber-400/80">Cronología</span>
              </div>
              {ticket && access.can("tickets.close") && (
                <button
                  type="button"
                  className="button-secondary rounded-full w-full py-1.5 text-xs flex items-center justify-center gap-1.5 border-amber-500/30 text-amber-300 hover:bg-amber-500/15 transition-colors"
                  onClick={() => { setEndAt(localDateTimeValue()); setStatus('CLOSED') }}
                >
                  <Check size={13} aria-hidden="true" />
                  <span>Finalizar ahora</span>
                </button>
              )}
              <p className="text-[11px] text-slate-400 leading-normal m-0">Fechas y horas de tu navegador. Puedes registrar una incidencia anterior; “Ahora” es solo un atajo.</p>
              <div className="space-y-3">
                <FormField describedBy={submitError ? "ticket-submit-error" : undefined} invalid={(submitError === "Completa los campos obligatorios antes de guardar." && !startAt.trim()) || apiInvalidFields.includes("start_at")} id="start-at" label="Inicio" required>
                  <div className="flex items-center gap-2">
                    <input disabled={!editable} id="start-at" type="datetime-local" step="60" className="form-input min-w-0" required value={startAt} onChange={(e) => setStartAt(e.target.value)} />
                    <button type="button" className="button-secondary rounded-full shrink-0" disabled={!editable} aria-label="Ahora de Inicio" onClick={() => setStartAt(localDateTimeValue())}>Ahora</button>
                  </div>
                </FormField>
                <FormField describedBy={submitError ? "ticket-submit-error" : undefined} invalid={submitError === "Fin debe ser igual o posterior a Inicio." || apiInvalidFields.includes("end_at")} id="end-at" label="Fin">
                  <div className="flex items-center gap-2">
                    <input disabled={!mayResolve} id="end-at" type="datetime-local" step="60" className="form-input min-w-0" value={endAt} onChange={(e) => setEndAt(e.target.value)} />
                    <button type="button" className="button-secondary rounded-full shrink-0" disabled={!mayResolve} aria-label="Ahora de Fin" onClick={() => setEndAt(localDateTimeValue())}>Ahora</button>
                  </div>
                </FormField>
              </div>
            </section>

            {/* TICKET INTERNO RELACIONADO */}
            <section aria-labelledby="internal-link-heading" className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-3">
              <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-purple-500/10 border border-purple-500/20 text-purple-400 text-xs" aria-hidden="true"><Link2 size={13} /></span>
                  <h2 id="internal-link-heading" className="text-xs font-bold font-mono text-white uppercase tracking-wider">Ticket interno relacionado</h2>
                </div>
                <span className="text-[11px] font-mono text-purple-400/80">Infraestructura</span>
              </div>
              <InternalTicketSelect value={internalTicketId} onChange={setInternalTicketId} disabled={submitting || !access.can("tickets.link")} />
            </section>

            {/* PANEL DE ACCIONES Y GUARDADO */}
            <div className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-4 lg:sticky lg:top-20">
              <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs font-mono font-bold" aria-hidden="true">✓</span>
                  <h3 className="text-xs font-bold font-mono text-white uppercase tracking-wider">Acciones</h3>
                </div>
                <span className="text-[11px] font-mono text-slate-500">{ticket ? 'Modificación' : 'Creación'}</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed m-0">
                {ticket
                  ? "Actualiza los datos operativos del ticket. Los cambios son registrados en la auditoría del sistema."
                  : "Registra la incidencia en el catálogo activo de tickets. La referencia correlativa se asignará automáticamente al guardar."}
              </p>

              {submitError && <FeedbackMessage id="ticket-submit-error" variant="error">{submitError}</FeedbackMessage>}

              <div className="pt-2 space-y-2.5">
                <button
                  type="submit"
                  className="button-primary rounded-full w-full py-2.5 text-sm font-semibold shadow-lg shadow-sky-500/25 flex items-center justify-center gap-2"
                  disabled={!editable || submitting || catalogLoading || Boolean(catalogError) || circuitLoading || Boolean(circuitError)}
                >
                  {submitting ? (ticket ? 'Guardando...' : 'Creando...') : (ticket ? 'Guardar cambios' : 'Guardar')}
                </button>
                <button
                  type="button"
                  className="button-secondary rounded-full w-full py-2 text-xs text-slate-300 hover:text-white flex items-center justify-center gap-1.5"
                  disabled={submitting}
                  onClick={() => navigate(ticket ? `/tickets/${ticket.id}` : '/tickets')}
                >
                  Cancelar
                </button>
              </div>
            </div>
          </div>
        </div>
      </fieldset>
    </form>
    {quickCreate === 'customer' && <QuickCatalogCreate kind="customer" onCancel={() => setQuickCreate(null)} onCreated={customerCreated} />}
    {quickCreate === 'circuit' && selectedCustomer && <QuickCatalogCreate kind="circuit" customer={selectedCustomer} onCancel={() => setQuickCreate(null)} onCreated={circuitCreated} />}
  </>
}
