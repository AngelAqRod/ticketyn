"""Explicit permission vocabulary and immutable defaults for this application version."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Permission:
    code: str
    label: str
    module: str
    requires: tuple[str, ...] = ()
    exclusive: bool = False

PERMISSIONS: dict[str, Permission] = {}
ACTION_LABELS = {'view': 'Consultar', 'create': 'Crear', 'edit': 'Editar', 'delete': 'Eliminar',
                 'export': 'Exportar', 'close': 'Cerrar', 'escalate': 'Gestionar escalamientos',
                 'followup': 'Agregar seguimiento', 'execute': 'Ejecutar', 'link': 'Gestionar vínculos',
                 'notify': 'Solicitar notificación', 'deactivate': 'Registrar baja', 'reactivate': 'Registrar reactivación',
                 'lookup': 'Consultar selector', 'manage': 'Administrar', 'test': 'Enviar prueba SMTP',
                 'authorize': 'Autorizar o desconectar OAuth2', 'preview': 'Vista previa', 'control': 'Pausar o reanudar',
                 'configure': 'Configurar seguridad', 'clean': 'Limpiar auditoría',
                 'move': 'Trasladar', 'set_active': 'Activar o desactivar'}

def register(module, actions, *, exclusive=(), lookup=False):
    for action in actions:
        code = f'{module}.{action}'
        requires = () if action in {'view', 'export', 'lookup'} else (f'{module}.lookup' if lookup else f'{module}.view',)
        # Modules with a single administrative capability have no artificial view action.
        if 'view' not in actions and not lookup:
            requires = ()
        PERMISSIONS[code] = Permission(code, ACTION_LABELS.get(action, action), module, requires, action in exclusive)

register('dashboard', ('view',))
for module in ('tickets', 'internal_tickets'):
    register(module, ('view', 'create', 'edit', 'close', 'escalate', 'followup', 'export', 'link'))
PERMISSIONS.pop('internal_tickets.link')
register('changes', ('view', 'create', 'edit', 'execute', 'link', 'followup', 'export'))
for module in ('customers', 'circuits'):
    register(module, ('view', 'create', 'edit', 'delete', 'lookup'))
for module in ('distribution_devices', 'distribution_ports'):
    register(module, ('view', 'lookup', 'create', 'edit', 'move', 'set_active', 'delete'))
register('activations', ('view', 'create', 'followup', 'notify', 'export'))
register('capacity_changes', ('view', 'execute', 'export'))
register('lifecycle', ('view', 'deactivate', 'reactivate', 'export'))
register('cpe', ('view', 'edit'))
CATALOGS = ('sectors', 'departments', 'incident_types', 'nodes', 'responsibles', 'positions',
            'escalation_reasons', 'service_types', 'deactivation_reasons', 'cpe_models',
            'internal_incident_types', 'providers', 'change_completion_types', 'change_types', 'port_nomenclatures')
for module in CATALOGS:
    register('catalogs.' + module, ('view', 'create', 'edit', 'lookup'))
register('catalogs.port_nomenclatures', ('view', 'create', 'edit', 'lookup', 'delete'))
for module in ('tickets', 'internal_tickets', 'changes', 'activations', 'capacity_changes', 'lifecycle', 'escalations'):
    register('reports.' + module, ('view', 'export') if module != 'escalations' else ('view',))
for module in ('ticket_number', 'internal_ticket_number', 'activation_number', 'change_number'):
    register('settings.' + module, ('view', 'edit'))
for module, actions in (('transport', ('view', 'edit', 'test')), ('oauth', ('view', 'edit', 'authorize')),
                        ('events', ('view', 'edit')), ('templates', ('view', 'edit', 'preview')),
                        ('processor', ('view', 'control'))):
    register('mail.' + module, actions)
# Existing quick forms use the same POST routes, but only create active records.
for module in ('customers', 'circuits', 'nodes'):
    code = 'context.' + module + '.create'
    dependency = 'catalogs.nodes.lookup' if module == 'nodes' else module + '.lookup'
    PERMISSIONS[code] = Permission(code, 'Creación rápida', 'context.' + module, (dependency,))
register('roles', ('manage',), exclusive=('manage',))
register('accounts', ('manage',))
register('sessions', ('manage',))
register('security', ('configure',), exclusive=('configure',))
register('audit', ('view', 'export', 'clean'), exclusive=('export', 'clean'))
for code, dependency in [('cpe.view','circuits.view'), ('mail.oauth.view','mail.transport.view')]:
    from dataclasses import replace
    PERMISSIONS[code] = replace(PERMISSIONS[code], requires=(dependency,))
EXCLUSIVE = frozenset(code for code, item in PERMISSIONS.items() if item.exclusive)

# No wildcard for ordinary roles: new modules/actions require an explicit decision here.
OPERATOR = frozenset({
    *(f'{module}.{action}' for module in ('distribution_devices', 'distribution_ports') for action in ('view', 'lookup', 'create', 'edit')),
    'dashboard.view',
    *(f'{module}.{action}' for module in ('tickets', 'internal_tickets') for action in ('view', 'create', 'edit', 'close', 'escalate', 'followup', 'export', 'link')),
    *(f'{module}.{action}' for module in ('customers', 'circuits') for action in ('view', 'create', 'edit', 'delete', 'lookup')),
    *(f'activations.{action}' for action in ('view', 'create', 'followup', 'notify', 'export')),
    'capacity_changes.view', 'capacity_changes.execute', 'capacity_changes.export',
    'lifecycle.view', 'lifecycle.deactivate', 'lifecycle.reactivate', 'lifecycle.export',
    'changes.view', 'changes.export', 'cpe.view', 'cpe.edit',
    *(f'catalogs.{module}.lookup' for module in CATALOGS),
    *(f'context.{module}.create' for module in ('customers', 'circuits', 'nodes')),
    *(f'reports.{module}.{action}' for module in ('tickets', 'internal_tickets', 'changes', 'activations', 'capacity_changes', 'lifecycle') for action in ('view', 'export')),
    'reports.escalations.view',
})
AUDITOR = frozenset({
    'catalogs.port_nomenclatures.view',
    *(f'{module}.{action}' for module in ('distribution_devices', 'distribution_ports') for action in ('view', 'lookup')),
    'dashboard.view',
    *(f'{module}.{action}' for module in ('tickets', 'internal_tickets', 'customers', 'circuits', 'activations', 'capacity_changes', 'lifecycle', 'changes') for action in ('view', 'export') if f'{module}.{action}' in PERMISSIONS),
    'customers.lookup', 'circuits.lookup', 'cpe.view',
    *(f'catalogs.{module}.lookup' for module in CATALOGS),
    *(f'reports.{module}.{action}' for module in ('tickets', 'internal_tickets', 'changes', 'activations', 'capacity_changes', 'lifecycle') for action in ('view', 'export')),
    'reports.escalations.view',
})
ADMIN_MODULES = frozenset({
    'distribution_devices', 'distribution_ports',
    'dashboard', 'tickets', 'internal_tickets', 'customers', 'circuits', 'activations', 'capacity_changes',
    'lifecycle', 'changes', 'cpe', 'accounts', 'sessions', 'audit',
    *('catalogs.' + key for key in CATALOGS),
    *('context.' + key for key in ('customers', 'circuits', 'nodes')),
    *('reports.' + key for key in ('tickets', 'internal_tickets', 'changes', 'activations', 'capacity_changes', 'lifecycle', 'escalations')),
    *('settings.' + key for key in ('ticket_number', 'internal_ticket_number', 'activation_number', 'change_number')),
    *('mail.' + key for key in ('transport', 'oauth', 'events', 'templates', 'processor')),
})
DEFAULT_GRANTS = {
    'SUPERADMIN': frozenset(PERMISSIONS),
    'ADMIN': frozenset(code for code, item in PERMISSIONS.items() if item.module in ADMIN_MODULES and not item.exclusive),
    'OPERATOR': OPERATOR & PERMISSIONS.keys(),
    'AUDITOR': AUDITOR,
}

# Read-only selectors required by existing forms/filters. These do not grant a catalog page or CRUD.
CONTEXT_READS = {
    'customers': {'tickets', 'activations', 'capacity_changes', 'lifecycle', 'circuits', 'reports.tickets', 'reports.activations', 'reports.capacity_changes', 'reports.lifecycle', 'reports.escalations'},
    'circuits': {'tickets', 'activations', 'capacity_changes', 'lifecycle', 'reports.tickets', 'reports.activations', 'reports.capacity_changes', 'reports.lifecycle', 'reports.escalations'},
    'nodes': {'tickets', 'internal_tickets', 'changes', 'circuits', 'activations', 'capacity_changes', 'lifecycle', 'reports.tickets', 'reports.internal_tickets', 'reports.changes', 'reports.activations', 'reports.capacity_changes', 'reports.lifecycle', 'reports.escalations'},
    'sectors': {'tickets', 'internal_tickets', 'changes', 'circuits', 'activations', 'capacity_changes', 'lifecycle', 'reports.tickets', 'reports.internal_tickets', 'reports.changes', 'reports.activations', 'reports.capacity_changes', 'reports.lifecycle', 'reports.escalations'},
    'departments': {'catalogs.responsibles', 'catalogs.positions', 'tickets', 'internal_tickets', 'changes', 'reports.tickets', 'reports.internal_tickets', 'reports.changes', 'reports.escalations'},
    'responsibles': {'tickets', 'internal_tickets', 'changes', 'activations', 'capacity_changes', 'lifecycle', 'reports.tickets', 'reports.internal_tickets', 'reports.changes', 'reports.activations', 'reports.capacity_changes', 'reports.lifecycle', 'reports.escalations'},
    'positions': {'tickets', 'internal_tickets', 'changes', 'catalogs.responsibles'},
    'incident_types': {'tickets', 'reports.tickets'}, 'internal_incident_types': {'internal_tickets', 'reports.internal_tickets'},
    'providers': {'internal_tickets', 'reports.internal_tickets'},
    'escalation_reasons': {'tickets', 'internal_tickets', 'reports.tickets', 'reports.internal_tickets', 'reports.escalations'},
    'service_types': {'circuits', 'activations', 'capacity_changes', 'lifecycle', 'reports.activations', 'reports.capacity_changes', 'reports.lifecycle'},
    'cpe_models': {'circuits', 'cpe', 'activations', 'capacity_changes', 'lifecycle', 'reports.activations', 'reports.capacity_changes', 'reports.lifecycle'},
    'deactivation_reasons': {'lifecycle', 'reports.lifecycle'},
    'change_types': {'changes', 'reports.changes'}, 'change_completion_types': {'changes', 'reports.changes'},
}

def expanded_context(grants):
    effective = set(grants)
    if any(code.startswith('distribution_ports.') for code in grants):
        effective.add('catalogs.port_nomenclatures.lookup')
    if any(code.startswith(('distribution_devices.', 'distribution_ports.')) for code in grants):
        effective.add('catalogs.nodes.lookup')
    for resource, modules in CONTEXT_READS.items():
        if any(code.rsplit('.', 1)[0] in modules for code in grants):
            effective.add(f'{resource}.lookup' if resource in {'customers', 'circuits'} else f'catalogs.{resource}.lookup')
    return frozenset(effective)


def normalize_permissions(requested, previous=()):
    from fastapi import HTTPException
    result = set(requested)
    unknown = result - PERMISSIONS.keys()
    if unknown:
        raise HTTPException(422, 'Hay permisos desconocidos')
    if result & EXCLUSIVE:
        raise HTTPException(422, 'Las facultades exclusivas no pueden asignarse a roles personalizados')
    removed = set(previous) - result
    while True:
        invalid = {code for code in result if set(PERMISSIONS[code].requires) & removed}
        if not invalid:
            break
        result -= invalid
        removed |= invalid
    pending = list(result)
    while pending:
        for dependency in PERMISSIONS[pending.pop()].requires:
            if dependency not in result:
                result.add(dependency); pending.append(dependency)
    return frozenset(result)
