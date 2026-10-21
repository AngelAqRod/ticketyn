"""Closed inventory of existing HTTP operations. No implicit CRUD authorization."""
from dataclasses import dataclass
from starlette.routing import compile_path

@dataclass(frozen=True)
class Rule:
    all_of: tuple[str, ...] = ()
    any_of: tuple[str, ...] = ()
    public: bool = False
    self_service: bool = False
    fms_report: bool = False

RULES: dict[tuple[str, str], Rule] = {}

def route(method, path, *all_of, any_of=(), public=False, self_service=False, fms_report=False):
    key = method, path
    if key in RULES:
        raise RuntimeError('Política duplicada: ' + repr(key))
    RULES[key] = Rule(all_of, tuple(any_of), public, self_service, fms_report)

route('GET', '/health', public=True)
route('HEAD', '/health', public=True)
route('POST', '/api/auth/login', public=True)
for method, action in [('GET', 'me'), ('POST', 'activity'), ('POST', 'logout'), ('POST', 'password')]:
    route(method, '/api/auth/' + action, self_service=True)
route('GET', '/api/system/version', self_service=True)
for path in ('/docs', '/docs/oauth2-redirect', '/redoc', '/openapi.json'):
    route('GET', path, any_of=('roles.manage', 'accounts.manage'))

for resource, module in [('tickets', 'tickets'), ('internal-tickets', 'internal_tickets')]:
    base = '/api/' + resource
    report = 'reports.' + module
    route('GET', base, any_of=(module + '.view', report + '.view'))
    route('POST', base, module + '.create')
    route('GET', base + '/{id}', any_of=(module + '.view', *(['tickets.view', 'changes.view'] if module == 'internal_tickets' else [])))
    route('PATCH', base + '/{id}', any_of=(module + '.edit', module + '.close', *(['tickets.link'] if module == 'tickets' else [])))
    route('GET', base + '/export/{format}', any_of=(module + '.export', report + '.export'))
    route('GET', base + '/{id}/updates', module + '.view')
    route('POST', base + '/{id}/updates', module + '.followup')
    route('GET', base + '/{id}/escalations', module + '.view')
    route('POST', base + '/{id}/escalations', module + '.escalate')
    route('PATCH', base + '/{id}/escalations/{escalation_id}', module + '.escalate')
    route('POST', base + '/{id}/escalations/{escalation_id}/finish', module + '.escalate')
    route('GET', base + '/{id}/escalations/{escalation_id}/audit', module + '.view')
    route('GET', base + '/{id}/reports/internal/pdf', module + '.export')
# Linking uses the existing list operation with a compact contextual response.
RULES[('GET', '/api/internal-tickets')] = Rule(any_of=('internal_tickets.view', 'reports.internal_tickets.view', 'tickets.link', 'changes.link'))
route('GET', '/api/tickets/{id}/reports/customer/pdf', 'tickets.export')
route('GET', '/api/tickets/stats', 'tickets.view')
route('GET', '/api/internal-tickets/{id}/related', 'internal_tickets.view')
route('GET', '/api/escalations/summary', 'reports.escalations.view')
route('GET', '/api/escalations/tickets', 'reports.escalations.view')

for resource in ('customers', 'circuits'):
    route('GET', '/api/' + resource, any_of=(resource + '.view', resource + '.lookup'))
    route('GET', '/api/' + resource + '/{id}', any_of=(resource + '.view', resource + '.lookup'))
    route('POST', '/api/' + resource, any_of=(resource + '.create', 'context.' + resource + '.create'))
    route('PATCH', '/api/' + resource + '/{id}', resource + '.edit')
    route('DELETE', '/api/' + resource + '/{id}', resource + '.delete')
route('GET', '/api/circuits/{id}/operational-detail', any_of=('circuits.view', 'capacity_changes.execute'))
route('GET', '/api/circuits/{id}/cpe-configuration', 'cpe.view')
route('PATCH', '/api/circuits/{id}/cpe-configuration', 'cpe.edit')

CATALOG_PATHS = ('sectors', 'departments', 'incident-types', 'nodes', 'responsibles', 'positions',
                 'escalation-reasons', 'service-types', 'deactivation-reasons', 'cpe-models',
                 'internal-incident-types', 'providers', 'change-completion-types', 'change-types')
for resource in CATALOG_PATHS:
    module = 'catalogs.' + resource.replace('-', '_')
    route('GET', '/api/' + resource, any_of=(module + '.view', module + '.lookup'))
    if resource != 'deactivation-reasons':
        route('GET', '/api/' + resource + '/{id}', any_of=(module + '.view', module + '.lookup'))
    route('POST', '/api/' + resource, any_of=(module + '.create', 'context.nodes.create') if resource == 'nodes' else (module + '.create',))
    route('PATCH', '/api/' + resource + '/{id}', module + '.edit')

for resource, consumer in [('ticket-number', 'tickets'), ('internal-ticket-number', 'internal_tickets'),
                           ('activation-number', 'activations'), ('change-number', 'changes')]:
    module = 'settings.' + resource.replace('-', '_')
    route('GET', '/api/settings/' + resource, module + '.view')
    route('PATCH', '/api/settings/' + resource, module + '.edit')

for resource, module in [('activations', 'activations'), ('capacity-changes', 'capacity_changes'), ('circuit-lifecycle', 'lifecycle')]:
    route('GET', '/api/' + resource, any_of=(module + '.view', 'reports.' + module + '.view', *(['mail.templates.preview'] if module == 'activations' else [])))
    route('POST', '/api/' + resource, any_of=('lifecycle.deactivate', 'lifecycle.reactivate') if module == 'lifecycle' else (module + ('.create' if module == 'activations' else '.execute'),))
    route('GET', '/api/' + resource + '/export/{format}', any_of=(module + '.export', 'reports.' + module + '.export'))
route('GET', '/api/activations/{id}', 'activations.view')
route('GET', '/api/activations/{id}/reports/pdf', 'activations.export')
route('GET', '/api/activations/{id}/interventions', 'activations.view')
route('POST', '/api/activations/{id}/interventions', 'activations.followup')
route('GET', '/api/activations/{id}/notification', 'activations.view')
route('POST', '/api/activations/{id}/notification', 'activations.notify')
for suffix in ('summary', 'details', 'export/pdf'):
    route('GET', '/api/fms/reports/{kind}/' + suffix, fms_report=True)

route('GET', '/api/changes', any_of=('changes.view', 'reports.changes.view'))
route('POST', '/api/changes', 'changes.create')
route('GET', '/api/changes/{id}', 'changes.view')
route('PATCH', '/api/changes/{id}', any_of=('changes.edit', 'changes.execute', 'changes.link'))
route('GET', '/api/changes/{id}/updates', 'changes.view')
route('POST', '/api/changes/{id}/updates', 'changes.followup')
route('GET', '/api/changes/{id}/audit', 'changes.view')
route('GET', '/api/changes/export/{format}', any_of=('changes.export', 'reports.changes.export'))
route('GET', '/api/changes/{id}/reports/pdf', 'changes.export')
route('GET', '/api/change-reports/summary', 'reports.changes.view')
route('GET', '/api/change-reports/export/{format}', 'reports.changes.export')
for prefix, module in [('/api/reports', 'tickets'), ('/api/reports/internal-tickets', 'internal_tickets')]:
    route('GET', prefix + '/summary', 'reports.' + module + '.view')
    route('GET', prefix + '/export/{format}', 'reports.' + module + '.export')

base = '/api/mail-notifications'
for resource, module in [('smtp', 'transport'), ('oauth', 'oauth')]:
    route('GET', base + '/' + resource, 'mail.' + module + '.view')
    route('PATCH', base + '/' + resource, 'mail.' + module + '.edit')
route('POST', base + '/smtp/test', 'mail.transport.test')
route('POST', base + '/oauth/authorize', 'mail.oauth.authorize')
route('GET', base + '/oauth/callback', 'mail.oauth.authorize')
route('POST', base + '/oauth/disconnect', 'mail.oauth.authorize')
route('GET', base + '/events', any_of=('mail.events.view', 'mail.templates.view'))
route('GET', base + '/events/{event_key}', any_of=('mail.events.view', 'mail.templates.view'))
route('PATCH', base + '/events/{event_key}', 'mail.events.edit')
route('GET', base + '/events/{event_key}/fields', 'mail.templates.view')
route('GET', base + '/events/{event_key}/template', 'mail.templates.view')
route('PATCH', base + '/events/{event_key}/template', 'mail.templates.edit')
route('POST', base + '/events/{event_key}/preview', 'mail.templates.preview')
for resource in ('processor', 'requests'):
    route('GET', base + '/' + resource, 'mail.processor.view')
for action in ('pause', 'resume'):
    route('POST', base + '/processor/' + action, 'mail.processor.control')

# Phase 2 role contracts, without account/profile/audit administration screens.
route('GET', '/api/security/permissions', 'roles.manage')
route('GET', '/api/security/roles', any_of=('roles.manage', 'accounts.manage'))
route('GET', '/api/security/roles/{id}', any_of=('roles.manage', 'accounts.manage'))
route('POST', '/api/security/roles', 'roles.manage')
route('PATCH', '/api/security/roles/{id}', 'roles.manage')
route('DELETE', '/api/security/roles/{id}', 'roles.manage')
route('POST', '/api/security/roles/{id}/duplicate', 'roles.manage')

# Phase 3 self-service and scoped administration. Definitions stay independent.
for path in ('/api/auth/profile', '/api/auth/sessions'):
    route('GET', path, self_service=True)
route('POST', '/api/auth/sessions/close-others', self_service=True)
route('POST', '/api/auth/sessions/{session_id}/revoke', self_service=True)
route('GET', '/api/responsibles/access', 'accounts.manage')
for method in ('GET', 'POST', 'PATCH'):
    route(method, '/api/responsibles/{id}/access', 'accounts.manage')
route('POST', '/api/responsibles/{id}/access/password', 'accounts.manage')
route('GET', '/api/security/sessions', 'sessions.manage')
route('POST', '/api/security/sessions/{session_id}/revoke', 'sessions.manage')
route('GET', '/api/security/audit', 'audit.view')
route('GET', '/api/security/audit/retention', 'security.configure')
route('PATCH', '/api/security/audit/retention', 'security.configure')

_MATCHERS = sorted(((method, path, compile_path(path)[0], rule) for (method, path), rule in RULES.items()),
                   key=lambda entry: (entry[1].count('{'), -len(entry[1])))

def resolve(method, path):
    for expected_method, template, regex, rule in _MATCHERS:
        match = regex.fullmatch(path)
        if expected_method == method and match:
            return template, rule, match.groupdict()
    return None


def allowed(rule, permissions, params, template):
    if rule.public or rule.self_service:
        return True
    if rule.fms_report:
        module = {'activations': 'activations', 'capacity-changes': 'capacity_changes', 'circuit-lifecycle': 'lifecycle'}.get(params.get('kind'))
        # Invalid kinds are left to normal request validation, only for a role with a report grant.
        if module is None:
            return any(code.startswith('reports.') for code in permissions)
        return f'reports.{module}.{"export" if template.endswith("export/pdf") else "view"}' in permissions
    return all(code in permissions for code in rule.all_of) and (not rule.any_of or any(code in permissions for code in rule.any_of))


def validate_coverage(app):
    from ticketyn.security.permissions import PERMISSIONS
    missing = [(method.upper(), path) for path, methods in app.openapi()['paths'].items() for method in methods
               if method.upper() in {'GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'HEAD', 'OPTIONS'} and (method.upper(), path) not in RULES]
    if missing:
        raise RuntimeError('Endpoints sin política explícita: ' + repr(missing))
    for rule in RULES.values():
        unknown = (set(rule.all_of) | set(rule.any_of)) - PERMISSIONS.keys()
        if unknown:
            raise RuntimeError('Permisos desconocidos: ' + repr(unknown))
