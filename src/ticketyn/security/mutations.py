"""Additional permissions for existing combined operations, checked before writes."""
from ticketyn.security.roles import require


def ticket_mutation(actor, module, values, item=None):
    if item is not None:
        for key, value in values.items():
            if key == 'internal_ticket_id' and module == 'tickets':
                continue
            before = getattr(item, key, None)
            before = before.value if hasattr(before, 'value') else before
            after = value.value if hasattr(value, 'value') else value
            if before != after:
                action = '.close' if key == 'status' or (key in {'end_at', 'resolution'} and module + '.edit' not in actor.permissions) else '.edit'
                require(actor, module + action)
    if 'status' in values:
        current = item.status.value if item is not None and hasattr(item.status, 'value') else item.status if item is not None else 'OPEN'
        new = values['status'].value if hasattr(values['status'], 'value') else values['status']
        if new != current:
            require(actor, module + '.close')
    if module == 'tickets' and 'internal_ticket_id' in values:
        if values['internal_ticket_id'] != (item.internal_ticket_id if item is not None else None):
            require(actor, 'tickets.link')


def change_mutation(actor, values, item=None):
    if item is not None:
        for key, value in values.items():
            if key in {'status', 'actual_start', 'actual_end', 'completion_type_id', 'internal_ticket_ids'}:
                continue
            if key == 'support_ids':
                before = {person.person_id for person in item.support}
                changed = set(value) != before
            else:
                changed = value != getattr(item, key, None)
            if changed:
                require(actor, 'changes.edit' if key != 'final_notes' or 'changes.edit' in actor.permissions else 'changes.execute')
    defaults = {'status': 'SCHEDULED', 'actual_start': None, 'actual_end': None, 'completion_type_id': None}
    if any(key in values and values[key] != (getattr(item, key) if item is not None else default)
           for key, default in defaults.items()):
        require(actor, 'changes.execute')
    if 'internal_ticket_ids' in values:
        previous = {link.internal_ticket_id for link in item.tickets} if item is not None else set()
        if set(values['internal_ticket_ids']) != previous:
            require(actor, 'changes.link')


def circuit_mutation(actor, item, values):
    if 'sector_id' in values and values['sector_id'] != item.sector_id:
        # Existing sector correction also writes recent client tickets transactionally.
        require(actor, 'tickets.edit')
    if 'active' in values and values['active'] != item.active:
        require(actor, 'lifecycle.reactivate' if values['active'] else 'lifecycle.deactivate')


def contextual_creation(actor, resource, values):
    full = 'catalogs.nodes.create' if resource == 'nodes' else resource + '.create'
    if full not in actor.permissions:
        require(actor, 'context.' + resource + '.create')
        if values.get('active', True) is not True:
            from fastapi import HTTPException
            raise HTTPException(403, 'La creación rápida solo permite registros activos')
