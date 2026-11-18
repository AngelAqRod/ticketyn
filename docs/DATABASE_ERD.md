# Diagrama Entidad-Relación — Ticketyn (v0.8.0+)

Este documento presenta la arquitectura de datos relacional de **Ticketyn**, organizada según los principios de modelado de dominio limpio y los dominios funcionales del sistema.

---

## 1. Principios Arquitectónicos del Modelo de Datos

1. **Identidad Única de Personas y Cuentas:**
   - La tabla `responsibles` representa la identidad única de toda persona en Ticketyn (operadores, ingenieros NOC, administradores). No existe una tabla `users` paralela.
   - Las tres dimensiones de estado en `responsibles`:
     - `active`: Estado operativo (si es falso, invalida sesiones inmediatamente).
     - `access_granted`: Autorización administrativa persistente para ingresar al sistema.
     - `operational_selectable`: Disponibilidad para figurar en selectores operativos de tickets y circuitos.
2. **Topología de Red e Infraestructura de Distribución:**
   - Separación estricta entre la **infraestructura viva** (`circuits`, `distribution_devices`, `distribution_ports`) y las **instantáneas históricas inmutables** en FMS (`activations`).
   - Las claves compuestas (`node_id`, `distribution_device_id`, `distribution_port_id`) garantizan coherencia física: un puerto pertenece a un equipo y el equipo a un nodo.
3. **Desacoplamiento Operativo:**
   - Los **Tickets de Clientes** (`tickets`) dependen de clientes y circuitos.
   - Los **Tickets Internos** (`internal_tickets`) representan fallas de infraestructura troncal/proveedor y carecen de cliente o circuito.
   - Las **Operaciones FMS** registran el ciclo de vida del circuito con datos técnicos inmutables.
   - El **Control de Cambios** planifica ventanas de mantenimiento con equipo de soporte múltiple y asociación a tickets internos.

---

## 2. Diagrama ER Maestro (Núcleo del Sistema)

El siguiente diagrama ilustra el núcleo de entidades operativas y sus relaciones cardinales principales:

```mermaid
erDiagram
    CUSTOMERS ||--o{ CIRCUITS : "posee"
    NODES ||--o{ CIRCUITS : "ubica"
    SECTORS ||--o{ CIRCUITS : "clasifica"

    NODES ||--o{ DISTRIBUTION_DEVICES : "aloja"
    DISTRIBUTION_DEVICES ||--o{ DISTRIBUTION_PORTS : "contiene"
    CIRCUITS }o--o| DISTRIBUTION_PORTS : "conecta_a"

    DEPARTMENTS ||--o{ POSITIONS : "estructura"
    DEPARTMENTS ||--o{ RESPONSIBLES : "pertenece"
    POSITIONS ||--o{ RESPONSIBLES : "asigna_cargo"

    CUSTOMERS ||--o{ TICKETS : "reporta"
    CIRCUITS ||--o{ TICKETS : "afecta"
    RESPONSIBLES ||--o{ TICKETS : "atiende"
    INTERNAL_TICKETS ||--o{ TICKETS : "agrupa_opcional"

    RESPONSIBLES ||--o{ INTERNAL_TICKETS : "atiende"
    PROVIDERS ||--o{ INTERNAL_TICKETS : "involucra"

    CIRCUITS ||--o{ ACTIVATIONS : "activa"
    RESPONSIBLES ||--o{ ACTIVATIONS : "ejecuta"
    CIRCUITS ||--o{ CAPACITY_CHANGES : "modifica_ancho_banda"

    RESPONSIBLES ||--o{ MAINTENANCE_CHANGES : "gestiona"
    MAINTENANCE_CHANGES ||--o{ CHANGE_TICKETS : "asocia"
    INTERNAL_TICKETS ||--o{ CHANGE_TICKETS : "vinculado_a"

    CUSTOMERS ||--o{ INSTALLATION_ORDERS : "solicita"
    CIRCUITS |o--o| INSTALLATION_ORDERS : "origina"
```

---

## 3. Diagramas ER por Dominio Funcional

### A. Clientes, Circuitos y Topología de Distribución

Representa la planta externa, clientes y puertos de distribución:

```mermaid
erDiagram
    CUSTOMERS {
        int id PK
        string customer_code UK
        string name
        boolean active
        datetime created_at
    }

    SECTORS {
        int id PK
        string name UK
        boolean active
    }

    NODES {
        int id PK
        string name UK
        boolean active
    }

    SERVICE_TYPES {
        int id PK
        string name UK
        boolean active
    }

    CPE_MODELS {
        int id PK
        string name UK
        boolean active
    }

    PORT_NOMENCLATURES {
        int id PK
        string name
        string prefix UK
        text_array formats
        boolean active
    }

    DISTRIBUTION_DEVICES {
        int id PK
        int node_id FK
        string name
        text description
        boolean active
    }

    DISTRIBUTION_PORTS {
        int id PK
        int distribution_device_id FK
        int nomenclature_id FK
        string numbering_format
        jsonb number_components
        string name
        text description
        boolean active
    }

    CIRCUITS {
        int id PK
        int customer_id FK
        int node_id FK
        int sector_id FK
        int service_type_id FK
        int cpe_model_id FK
        int distribution_device_id FK
        int distribution_port_id FK
        string circuit_code UK
        text description
        inet cpe_management_ip
        text cpe_configuration
        decimal initial_capacity
        string initial_capacity_unit
        boolean active
        datetime created_at
    }

    CUSTOMERS ||--o{ CIRCUITS : "tiene"
    NODES ||--o{ CIRCUITS : "termina_en"
    SECTORS ||--o{ CIRCUITS : "pertenece_a"
    SERVICE_TYPES ||--o{ CIRCUITS : "tipo"
    CPE_MODELS ||--o{ CIRCUITS : "equipo_cpe"
    NODES ||--o{ DISTRIBUTION_DEVICES : "contiene"
    DISTRIBUTION_DEVICES ||--o{ DISTRIBUTION_PORTS : "posee"
    PORT_NOMENCLATURES ||--o{ DISTRIBUTION_PORTS : "aplica_formato"
    DISTRIBUTION_DEVICES ||--o{ CIRCUITS : "asigna_equipo"
    DISTRIBUTION_PORTS ||--o{ CIRCUITS : "asigna_puerto"
```

---

### B. Tickets de Clientes y Escalamientos NOC

Flujo de incidentes de clientes con bitácoras, escalamientos por puestos y acuses (ACK):

```mermaid
erDiagram
    TICKETS {
        int id PK
        int ticket_number UK
        string reference UK
        string title
        text description
        text resolution
        text customer_description
        text customer_resolution
        int customer_id FK
        int circuit_id FK
        int node_id FK
        int sector_id FK
        int department_id FK
        int incident_type_id FK
        int responsible_id FK
        int initial_position_id FK
        int internal_ticket_id FK
        int closed_seconds
        string status
        datetime start_at
        datetime end_at
        datetime created_at
        datetime updated_at
    }

    TICKET_UPDATES {
        int id PK
        int ticket_id FK
        int responsible_id FK
        text content
        datetime occurred_at
        datetime created_at
    }

    ESCALATION_REASONS {
        int id PK
        string name UK
        text description
        boolean active
    }

    TICKET_ESCALATIONS {
        int id PK
        int ticket_id FK
        int requester_id FK
        int recipient_id FK
        int reason_id FK
        int department_id FK
        int position_id FK
        string recipient_level
        string recipient_position_name
        text recipient_department_name
        text description
        string status
        datetime started_at
        datetime finished_at
        datetime created_at
        datetime updated_at
    }

    TICKET_ESCALATION_ACKS {
        int id PK
        int ticket_id FK
        int responsible_id FK
        datetime ack_until
        datetime created_at
    }

    TICKETS ||--o{ TICKET_UPDATES : "registra_seguimiento"
    TICKETS ||--o{ TICKET_ESCALATIONS : "escala_a"
    ESCALATION_REASONS ||--o{ TICKET_ESCALATIONS : "motivo"
    TICKETS ||--o{ TICKET_ESCALATION_ACKS : "silencia_notificacion"
```

---

### C. Tickets Internos (Infraestructura y Proveedores)

Incidentes que afectan la red troncal sin impactar directamente a un solo circuito/cliente:

```mermaid
erDiagram
    PROVIDERS {
        int id PK
        string name UK
        text description
        boolean active
    }

    INTERNAL_INCIDENT_TYPES {
        int id PK
        string name UK
        boolean active
    }

    INTERNAL_TICKETS {
        int id PK
        int ticket_number UK
        string reference UK
        string title
        text description
        text resolution
        int sector_id FK
        int node_id FK
        int department_id FK
        int incident_type_id FK
        int provider_id FK
        int responsible_id FK
        int initial_position_id FK
        int closed_seconds
        string status
        datetime start_at
        datetime end_at
        datetime created_at
        datetime updated_at
    }

    INTERNAL_TICKET_UPDATES {
        int id PK
        int ticket_id FK
        int responsible_id FK
        text content
        datetime occurred_at
        datetime created_at
    }

    INTERNAL_ESCALATIONS {
        int id PK
        int ticket_id FK
        int requester_id FK
        int recipient_id FK
        int reason_id FK
        int department_id FK
        int position_id FK
        string status
        text description
        datetime started_at
        datetime finished_at
    }

    INTERNAL_TICKET_ESCALATION_ACKS {
        int id PK
        int ticket_id FK
        int responsible_id FK
        datetime ack_until
        datetime created_at
    }

    PROVIDERS ||--o{ INTERNAL_TICKETS : "proveedor_afectado"
    INTERNAL_INCIDENT_TYPES ||--o{ INTERNAL_TICKETS : "clasifica"
    INTERNAL_TICKETS ||--o{ INTERNAL_TICKET_UPDATES : "seguimiento"
    INTERNAL_TICKETS ||--o{ INTERNAL_ESCALATIONS : "escala"
    INTERNAL_TICKETS ||--o{ INTERNAL_TICKET_ESCALATION_ACKS : "acusa"
```

---

### D. Gestión Operativa FMS (Ciclo de Vida de Circuitos)

Operaciones técnicas con instantáneas históricas preservadas:

```mermaid
erDiagram
    ACTIVATIONS {
        int id PK
        int circuit_id FK
        int responsible_id FK
        int node_id FK
        int sector_id FK
        int activation_number UK
        string reference UK
        boolean distribution_recorded
        string distribution_device_name
        string distribution_port_name
        text customer_name_snapshot
        text circuit_code_snapshot
        text activation_notes
        text customer_activation_notes
        text cpe_activation
        string service_type_name
        decimal initial_capacity
        string initial_capacity_unit
        datetime effective_at
        datetime created_at
    }

    ACTIVATION_INTERVENTIONS {
        int id PK
        int activation_id FK
        int responsible_id FK
        text content
        datetime occurred_at
        datetime created_at
    }

    CAPACITY_CHANGES {
        int id PK
        int circuit_id FK
        int responsible_id FK
        int node_id FK
        int sector_id FK
        string operation_type
        decimal previous_capacity
        string previous_unit
        decimal new_capacity
        string new_unit
        text description
        datetime effective_at
        datetime created_at
    }

    DEACTIVATION_REASONS {
        int id PK
        string name UK
        text description
        boolean active
    }

    CIRCUIT_LIFECYCLE_OPERATIONS {
        int id PK
        int circuit_id FK
        int responsible_id FK
        int reason_id FK
        int node_id FK
        int sector_id FK
        string operation_type
        text notes
        datetime effective_at
        datetime created_at
    }

    CIRCUITS ||--o{ ACTIVATIONS : "historial_activacion"
    ACTIVATIONS ||--o{ ACTIVATION_INTERVENTIONS : "intervenciones"
    CIRCUITS ||--o{ CAPACITY_CHANGES : "historial_capacidad"
    CIRCUITS ||--o{ CIRCUIT_LIFECYCLE_OPERATIONS : "bajas_reactivaciones"
    DEACTIVATION_REASONS ||--o{ CIRCUIT_LIFECYCLE_OPERATIONS : "motivo_baja"
```

---

### E. Control de Cambios (Ventanas de Mantenimiento)

Planificación de ventanas NOC, asignación de soporte técnico múltiple y vinculación con tickets internos:

```mermaid
erDiagram
    CHANGE_TYPES {
        int id PK
        string name UK
        text description
        boolean active
    }

    CHANGE_COMPLETION_TYPES {
        int id PK
        string name UK
        text description
        boolean applies_efficiency
        boolean active
    }

    MAINTENANCE_CHANGES {
        int id PK
        int ticket_number UK
        string reference UK
        string title
        text description
        int sector_id FK
        int node_id FK
        int change_type_id FK
        int manager_id FK
        string manager_name
        int department_id FK
        string department_name
        string status
        datetime proposed_start
        datetime proposed_end
        datetime actual_start
        datetime actual_end
        int completion_type_id FK
        string completion_name
        boolean efficiency_eligible
        text final_notes
        datetime created_at
        datetime updated_at
    }

    CHANGE_SUPPORT {
        int change_id PK_FK
        int person_id PK_FK
        string person_name
    }

    CHANGE_TICKETS {
        int change_id PK_FK
        int internal_ticket_id PK_FK
    }

    CHANGE_UPDATES {
        int id PK
        int change_id FK
        int responsible_id FK
        string responsible_name
        datetime occurred_at
        text content
        datetime created_at
    }

    CHANGE_TYPES ||--o{ MAINTENANCE_CHANGES : "tipo_cambio"
    CHANGE_COMPLETION_TYPES ||--o{ MAINTENANCE_CHANGES : "tipo_cierre"
    MAINTENANCE_CHANGES ||--o{ CHANGE_SUPPORT : "personal_apoyo"
    MAINTENANCE_CHANGES ||--o{ CHANGE_TICKETS : "asocia_ticket_interno"
    MAINTENANCE_CHANGES ||--o{ CHANGE_UPDATES : "bitacora"
```

---

### F. Estructura Organizacional, Cuentas y Seguridad RBAC

Modelado de la jerarquía NOC y control de acceso:

```mermaid
erDiagram
    DEPARTMENTS {
        int id PK
        string name UK
        boolean active
    }

    POSITIONS {
        int id PK
        int department_id FK
        string name
        text description
        string escalation_mode
        int general_escalation_time_minutes
        boolean active
    }

    POSITION_ESCALATION_DESTINATIONS {
        int id PK
        int position_id FK
        int target_position_id FK
        int time_minutes
        int order_index
    }

    SECURITY_ROLES {
        int id PK
        string code UK
        string name UK
        text description
        int revision
    }

    SECURITY_PERMISSIONS {
        string code PK
        string description
    }

    SECURITY_ROLE_PERMISSIONS {
        int role_id PK_FK
        string permission_code PK_FK
    }

    RESPONSIBLES {
        int id PK
        string name UK
        int department_id FK
        int position_id FK
        boolean operational_selectable
        boolean access_granted
        string username UK
        string password_hash
        int security_role_id FK
        boolean password_change_required
        bigint access_revision
        string preferred_home_page
        string attention_level
        boolean active
        datetime created_at
    }

    DEPARTMENTS ||--o{ POSITIONS : "contiene"
    POSITIONS ||--o{ POSITION_ESCALATION_DESTINATIONS : "origen"
    POSITIONS ||--o{ POSITION_ESCALATION_DESTINATIONS : "destino"
    DEPARTMENTS ||--o{ RESPONSIBLES : "departamento"
    POSITIONS ||--o{ RESPONSIBLES : "cargo"
    SECURITY_ROLES ||--o{ RESPONSIBLES : "rol_seguridad"
    SECURITY_ROLES ||--o{ SECURITY_ROLE_PERMISSIONS : "asigna"
    SECURITY_PERMISSIONS ||--o{ SECURITY_ROLE_PERMISSIONS : "concede"
```

---

### G. Órdenes de Instalación y Solicitudes Administrativas

Antecedentes documentales y requerimientos recibidos:

```mermaid
erDiagram
    INSTALLATION_ORDERS {
        int id PK
        string reference UK
        string external_reference
        int customer_id FK
        string service
        string location
        string contact
        string phone
        datetime requested_at
        text notes
        int created_by FK
        int circuit_id FK_UK
        datetime created_at
        datetime updated_at
    }

    INSTALLATION_REQUESTS {
        int id PK
        string mailbox
        string folder
        bigint uidvalidity
        bigint uid
        string checksum
        string sender
        string subject
        text body
        datetime received_at
        string state
        int reviewer_id FK
        int order_id FK_UK
        text discard_reason
        datetime created_at
        datetime updated_at
    }

    ADMIN_REQUEST_TYPES {
        int id PK
        string name UK
        text description
        boolean active
    }

    ADMIN_REQUESTS {
        int id PK
        string reference UK
        int request_type_id FK
        int responsible_id FK
        int customer_id FK
        int circuit_id FK
        string requester_name
        string requester_channel
        datetime requested_at
        text description
        datetime created_at
        datetime updated_at
    }

    ADMIN_REQUEST_LINKS {
        int id PK
        int admin_request_id FK
        int ticket_id FK
        int internal_ticket_id FK
        int change_id FK
        datetime created_at
    }

    CUSTOMERS ||--o{ INSTALLATION_ORDERS : "cliente"
    CIRCUITS |o--o| INSTALLATION_ORDERS : "circuito_creado"
    INSTALLATION_ORDERS |o--o| INSTALLATION_REQUESTS : "procesada_desde"
    ADMIN_REQUEST_TYPES ||--o{ ADMIN_REQUESTS : "tipo"
    CUSTOMERS ||--o{ ADMIN_REQUESTS : "cliente_opcional"
    CIRCUITS ||--o{ ADMIN_REQUESTS : "circuito_opcional"
    ADMIN_REQUESTS ||--o{ ADMIN_REQUEST_LINKS : "vincula_operaciones"
```

---

## 4. Invariantes de Integridad y Reglas Críticas del Esquema

1. **Restricción de Jerarquía de Distribución:**
   - Un circuito no puede tener `distribution_device_id` sin tener `node_id`.
   - Un circuito no puede tener `distribution_port_id` sin tener `distribution_device_id`.
   - Las claves foráneas compuestas garantizan que el puerto pertenece al equipo especificado y el equipo al nodo especificado.
2. **Instantáneas Históricas vs Estado Vivo en FMS:**
   - En `activations`, si `distribution_recorded = true`, se capturan `distribution_device_name` y `distribution_port_name` como texto inmutable. Modificaciones futuras en la tabla `circuits` no alteran los registros históricos.
   - En activaciones previas a v0.8.0, `distribution_recorded = false` indica que la infraestructura histórica no fue registrada (se presenta como «No registrado»).
3. **Escalamientos:**
   - Escalar un ticket (`tickets` o `internal_tickets`) crea un registro en `ticket_escalations` o `internal_escalations`.
   - **Regla sagrada de Ticketyn:** El escalamiento **nunca** modifica el `responsible_id` del ticket original.
4. **Protección del Superadministrador:**
   - Está prohibido desactivar, degradar de rol o retirar facultades al último Superadministrador activo mediante comprobación en `lock_security(session)`.
