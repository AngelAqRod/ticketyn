"""Read-only plain-text/HTML renderer shared by previews and SMTP.

Paths come exclusively from the server field registry. No client attribute paths,
expression evaluation, persistence or transport operations are permitted here.
"""
import re
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, func
from ticketyn.api.fms_exports import capacity_text
from ticketyn.models.fms import CapacityChange
from ticketyn.notifications.fields import EVENTS, FIELD_REGISTRY
from ticketyn.notifications.html import BodyBlock, render_html
from ticketyn.schemas.mail_templates import MailTemplate, PreviewResponse

def join_subject_elements(elements):
    """One space at block boundaries; omit blank values and preserve separators."""
    return ' '.join(value for element in elements if (value := ' '.join(element.split())))


def optional_capacity(value, unit):
    return capacity_text(value, unit) if value is not None and unit is not None else ''



def validate_template(event_key: str, template: MailTemplate):
    registry = {field.id: field for field in FIELD_REGISTRY[event_key]}
    if any(block.type == 'field' and block.field_id not in registry for block in [*template.subject, *template.body]):
        raise HTTPException(422, 'La plantilla contiene un campo no disponible para este evento.')
    return registry


def render_template(session, event_key, template, activation):
    registry = validate_template(event_key, template)
    cache = {}

    def path_value(path):
        parts = path.split('.')
        if parts[0] != 'Activation':
            raise ValueError('Unsupported registry source')
        value = activation
        for part in parts[1:]:
            value = getattr(value, part) if value is not None else None
        return value

    def resolve(identifier):
        if identifier in cache:
            return cache[identifier]
        field = registry[identifier]
        if field.resolver == 'latest_capacity_effective_now_or_initial':
            latest = session.scalar(select(CapacityChange).where(CapacityChange.circuit_id == activation.circuit_id, CapacityChange.effective_at <= func.now()).order_by(CapacityChange.effective_at.desc(), CapacityChange.id.desc()).limit(1))
            value = optional_capacity(latest.new_capacity, latest.new_unit) if latest else optional_capacity(activation.circuit.initial_capacity, activation.circuit.initial_capacity_unit)
        elif field.resolver == 'capacity':
            value = optional_capacity(*(path_value(path) for path in field.source_paths))
        else:
            value = path_value(field.source_paths[0])
            if value is None or value == '':
                value = ''
            elif field.format == 'datetime_guatemala':
                value = value.astimezone(ZoneInfo('America/Guatemala')).strftime('%d/%m/%Y %H:%M:%S')
            else:
                value = str(value)
        cache[identifier] = value
        return value

    # Multiline data is legitimate (notes/description); collapse it in a header
    # only. Static header text is rejected by the input schema instead.
    subject = join_subject_elements(block.text if block.type == 'text' else re.sub(r'[\x00-\x1f\x7f\u2028\u2029]+', ' ', resolve(block.field_id)) for block in template.subject)
    blocks = []
    html_blocks = []
    for block in template.body:
        if block.type == 'field':
            value = resolve(block.field_id)
            if value.strip():
                label = registry[block.field_id].label.upper() if block.label_mode == 'DEFAULT' else block.custom_label
                # Only activation notes place their content below the label;
                # other multiline fields retain their existing inline format.
                separator = '\n' if block.field_id == 'activation.activation_notes' else ' '
                blocks.append(('field', f'{label}:{separator}{value}'))
                html_blocks.append(BodyBlock('notes' if block.field_id == 'activation.activation_notes' else 'field', value, label))
        elif block.text.strip():
            blocks.append((block.type, block.text))
            html_blocks.append(BodyBlock(block.type, block.text))
        elif '\n' in block.text or '\r' in block.text:
            # A newline-only text block is an intentional separator, not empty.
            blocks.append(('spacing', block.text))
            html_blocks.append(BodyBlock('spacing', block.text))
    body = ''
    previous = None
    for kind, value in blocks:
        if previous is not None and kind != 'spacing' and previous != 'spacing':
            body += '\n' if kind == previous == 'field' else '\n\n'
        body += value
        previous = kind
    if len(subject.encode('utf-8')) > 998 or len(body) > 100000:
        raise HTTPException(422, 'El resultado supera el límite de 998 bytes de asunto o 100.000 caracteres de cuerpo. Reduce los bloques de la plantilla.')
    return PreviewResponse(subject=subject, body=body, html_body=render_html(EVENTS[event_key], html_blocks))
