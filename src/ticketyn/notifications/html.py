"""Fixed, offline email presentation of already resolved template blocks.

Technical Split — Opción 3 layout for Ticketyn v0.8.0.
- Electric Blue left vertical accent (#1768D5).
- Two-column split header (Left: wordmark & notification type; Right: badge, correlative & description).
- Clean light divider line below header (#E2E8F0).
- Visual sections with colored bar and title.
- Two-column balanced field pairs without individual cards or cell borders.
- Dedicated notes block with light blue-gray background (#F8FAFC) and emerald left border (#047857).
- Minimalist institutional footer (#F8FAFC).
- Compatible with desktop and mobile email clients, using presentation tables and inline CSS.
"""
from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class BodyBlock:
    kind: str
    value: str
    label: str = ''
    field_id: str = ''


def lines(value: str) -> str:
    # Escape first; only our own <br> elements can become markup. CSS preserves
    # spaces, while explicit breaks also work in clients with limited CSS.
    return escape(value, quote=True).replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>')


TEXT_STYLE = 'font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:22px;color:#1E293B;white-space:pre-wrap;word-wrap:break-word;overflow-wrap:anywhere;'
LABEL_STYLE = 'font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:16px;font-weight:600;letter-spacing:0.5px;color:#64748B;text-transform:uppercase;white-space:pre-wrap;word-wrap:break-word;overflow-wrap:anywhere;'
VALUE_STYLE = 'font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:20px;font-weight:600;color:#0F172A;margin-top:2px;white-space:pre-wrap;word-wrap:break-word;overflow-wrap:anywhere;'

DISTRIBUTION_FIELD_IDS = {
    'activation.distribution_device',
    'activation.distribution_port',
    'circuit.cpe_management_ip',
}

NOTES_FIELD_IDS = {
    'activation.activation_notes',
    'activation.customer_activation_notes',
}


def get_block_section(block: BodyBlock) -> tuple[str, str, str] | None:
    if block.kind == 'notes' or block.field_id in NOTES_FIELD_IDS:
        return ('notes', 'Notas técnicas de activación', '#047857')
    if block.field_id in DISTRIBUTION_FIELD_IDS:
        return ('distribution', 'Información técnica de distribución', '#0284C7')
    if block.kind == 'field':
        lbl = block.label.upper()
        if 'DISTRIBUCI' in lbl or 'GESTIÓN CPE' in lbl or 'GESTION CPE' in lbl:
            return ('distribution', 'Información técnica de distribución', '#0284C7')
        return ('activation', 'Información de activación', '#047857')
    return None


def render_section_header(title: str, color: str) -> str:
    escaped = escape(title, quote=True)
    return (
        '<tr><td colspan="2" class="ticketyn-section-header" style="padding:18px 0 8px 0;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0">'
        '<tr>'
        f'<td width="3" bgcolor="{color}" style="width:3px;background-color:{color};border-radius:1px;font-size:1px;line-height:1px;">&nbsp;</td>'
        f'<td style="padding-left:8px;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:16px;font-weight:bold;color:#0F172A;letter-spacing:0.5px;text-transform:uppercase;">{escaped}</td>'
        '</tr></table>'
        '</td></tr>'
    )


def render_html(
    title: str,
    blocks: list[BodyBlock],
    *,
    event_badge: str | None = None,
    reference: str | None = None,
    event_description: str | None = None,
    badge_color: str | None = None,
    badge_bg: str | None = None,
) -> str:
    heading = escape('Registro de activación' if title == 'Registro de activación FMS' else title, quote=True)

    if event_badge is None:
        title_lower = title.lower()
        if 'activación' in title_lower or 'fms' in title_lower:
            event_badge = 'FMS · ACTIVACIÓN'
            badge_color = badge_color or '#047857'
            badge_bg = badge_bg or '#ECFDF5'
            event_description = event_description or 'Nueva activación'
        else:
            event_badge = 'NOTIFICACIÓN'
            badge_color = badge_color or '#1768D5'
            badge_bg = badge_bg or '#EFF6FF'
            event_description = event_description or 'Notificación operativa'
    else:
        badge_color = badge_color or '#047857'
        badge_bg = badge_bg or '#ECFDF5'
        event_description = event_description or 'Nueva activación'

    if reference is None:
        for b in blocks:
            if b.field_id == 'activation.reference' and b.value.strip():
                reference = b.value.strip()
                break

    if reference and reference.strip():
        correlative_html = (
            f'<div style="font-family:\'Courier New\',Courier,monospace,Arial,sans-serif;'
            f'font-size:18px;line-height:24px;font-weight:bold;color:#0F172A;margin-top:4px;">{escape(reference.strip(), quote=True)}</div>'
        )
        description_html = (
            f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:16px;color:#64748B;margin-top:2px;">{escape(event_description, quote=True)}</div>'
        )
    else:
        correlative_html = ''
        description_html = (
            f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:18px;font-weight:600;color:#0F172A;margin-top:4px;">{escape(event_description, quote=True)}</div>'
        )

    rows = []
    fields = []
    rendered_sections = set()
    current_section = None

    def flush_fields():
        if not fields:
            return
        if len(fields) == 1:
            fields.append('<td class="ticketyn-empty" width="50%" style="width:50%;padding:0;"></td>')
        rows.append('<tr class="ticketyn-field-row">' + ''.join(fields) + '</tr>')
        fields.clear()

    for block in blocks:
        value = lines(block.value)
        label = lines(block.label)

        if block.kind == 'field':
            sec = get_block_section(block)
            if sec:
                sec_key, sec_title, sec_color = sec
                if sec_key != current_section:
                    flush_fields()
                    if sec_key not in rendered_sections:
                        rendered_sections.add(sec_key)
                        rows.append(render_section_header(sec_title, sec_color))
                    current_section = sec_key

            col_idx = len(fields)
            pad_left = "12px" if col_idx == 1 else "0"
            pad_right = "0" if col_idx == 1 else "12px"
            fields.append(
                f'<td class="ticketyn-field" width="50%" valign="top" style="width:50%;vertical-align:top;padding:8px {pad_right} 8px {pad_left};">'
                f'<div style="{LABEL_STYLE}">{label}:</div>'
                f'<div style="{VALUE_STYLE}">{value}</div></td>'
            )
            if len(fields) == 2:
                flush_fields()
            continue

        flush_fields()

        if block.kind == 'notes':
            sec = get_block_section(block)
            if sec:
                sec_key, sec_title, sec_color = sec
                if sec_key != current_section:
                    if sec_key not in rendered_sections:
                        rendered_sections.add(sec_key)
                        rows.append(render_section_header(sec_title, sec_color))
                    current_section = sec_key

            rows.append(
                '<tr><td colspan="2" style="padding:4px 0 16px 0;">'
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
                'bgcolor="#F2F6FC" style="width:100%;table-layout:fixed;border-left:3px solid #047857;background-color:#F2F6FC;border-radius:0 4px 4px 0;">'
                f'<tr><td style="padding:14px 16px;"><div style="{LABEL_STYLE}color:#047857;">{label}:</div>'
                f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:20px;color:#1E293B;margin-top:6px;white-space:pre-wrap;word-wrap:break-word;overflow-wrap:anywhere;">{value}</div></td></tr></table>'
                '</td></tr>'
            )
        elif block.kind == 'spacing':
            current_section = None
            rows.append(f'<tr><td colspan="2" style="{TEXT_STYLE}padding:0;">{value}</td></tr>')
        else:
            current_section = None
            rows.append(f'<tr><td colspan="2" style="{TEXT_STYLE}padding:12px 0;">{value}</td></tr>')

    flush_fields()
    content = ''.join(rows)

    escaped_badge = escape(event_badge, quote=True)

    return (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        'style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
        f'<title>Ticketyn — {heading}</title>'
        '<style>@media screen and (max-width:480px){'
        '.ticketyn-blocks,.ticketyn-blocks>tbody,.ticketyn-blocks>tbody>tr,.ticketyn-blocks>tbody>tr>td{display:block!important;width:100%!important;box-sizing:border-box;}'
        '.ticketyn-field{padding-left:0!important;padding-right:0!important;padding-bottom:12px!important;}'
        '.ticketyn-blocks>tbody>tr>.ticketyn-empty{display:none!important;}'
        '.ticketyn-content{padding-left:18px!important;padding-right:18px!important;}'
        '.ticketyn-header{padding-left:18px!important;padding-right:18px!important;}'
        '}</style></head>'
        '<body style="margin:0;padding:0;background-color:#F0F2F5;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'bgcolor="#F0F2F5" style="width:100%;background-color:#F0F2F5;">'
        '<tr><td align="center" style="padding:24px 8px;">'
        '<!--[if mso]><table role="presentation" width="640" align="center" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'bgcolor="#FFFFFF" style="width:100%;max-width:640px;table-layout:fixed;background-color:#FFFFFF;border:1px solid #E2E8F0;border-radius:6px;overflow:hidden;">'
        '<tr><td bgcolor="#FFFFFF" class="ticketyn-header" style="padding:22px 28px 18px;background-color:#FFFFFF;border-left:4px solid #1768D5;border-bottom:1px solid #E2E8F0;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;table-layout:fixed;">'
        '<tr><td align="left" valign="top" style="vertical-align:top;width:50%;">'
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:24px;line-height:28px;font-weight:bold;color:#1768D5;letter-spacing:-0.5px;">Ticketyn</div>'
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;line-height:16px;font-weight:bold;letter-spacing:1px;color:#64748B;text-transform:uppercase;margin-top:4px;">NOTIFICACIÓN OPERATIVA</div>'
        '</td>'
        '<td align="right" valign="top" style="vertical-align:top;width:50%;text-align:right;">'
        f'<div style="text-align:right;"><div style="display:inline-block;padding:3px 8px;font-family:Arial,Helvetica,sans-serif;font-size:10px;line-height:14px;font-weight:bold;letter-spacing:0.8px;color:{badge_color};background-color:{badge_bg};border-radius:4px;text-transform:uppercase;">{escaped_badge}</div></div>'
        f'{correlative_html}'
        f'{description_html}'
        '</td></tr></table>'
        '</td></tr>'
        '<tr><td class="ticketyn-content" style="padding:16px 28px 24px;background-color:#FFFFFF;">'
        '<table class="ticketyn-blocks" role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;table-layout:fixed;">'
        f'{content}</table></td></tr>'
        '<tr><td align="center" bgcolor="#F8FAFC" style="padding:14px 20px;background-color:#F8FAFC;font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:18px;color:#64748B;border-top:1px solid #E2E8F0;">Ticketyn · Gestión operativa</td></tr></table>'
        '<!--[if mso]></td></tr></table><![endif]-->'
        '</td></tr></table></body></html>'
    )
