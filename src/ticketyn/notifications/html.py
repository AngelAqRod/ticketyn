"""Fixed, offline email presentation of already resolved template blocks.

No user HTML, external assets, field resolution, persistence or transport here.
The existing text wordmark is used because the repository has no standalone logo
image: the application header combines that wordmark with a React icon.
"""
from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class BodyBlock:
    kind: str
    value: str
    label: str = ''


def lines(value: str) -> str:
    # Escape first; only our own <br> elements can become markup. CSS preserves
    # spaces, while explicit breaks also work in clients with limited CSS.
    return escape(value, quote=True).replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>')


TEXT_STYLE = 'font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:22px;color:#17263C;white-space:pre-wrap;word-wrap:break-word;overflow-wrap:anywhere;'
LABEL_STYLE = 'font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:18px;color:#64748B;white-space:pre-wrap;word-wrap:break-word;overflow-wrap:anywhere;'


def render_html(title: str, blocks: list[BodyBlock]) -> str:
    rows = []
    fields = []

    def flush_fields():
        if not fields:
            return
        # A vacant right cell preserves the position of an odd field. Never
        # borrow a later field across notes, text or explicit spacing blocks.
        if len(fields) == 1:
            fields.append('<td class="ticketyn-empty" width="50%" style="width:50%;padding:0;"></td>')
        rows.append('<tr class="ticketyn-field-row">' + ''.join(fields) + '</tr>')
        fields.clear()

    for block in blocks:
        value = lines(block.value)
        label = lines(block.label)
        if block.kind == 'field':
            fields.append(
                '<td class="ticketyn-field" width="50%" valign="top" style="width:50%;vertical-align:top;padding:10px 12px 10px 0;">'
                f'<div style="{LABEL_STYLE}">{label}:</div>'
                f'<div style="{TEXT_STYLE}margin-top:3px;">{value}</div></td>')
            if len(fields) == 2:
                flush_fields()
            continue
        flush_fields()
        if block.kind == 'notes':
            rows.append(
                '<tr><td colspan="2" style="padding:12px 0;">'
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
                'bgcolor="#F2F6FC" style="width:100%;table-layout:fixed;border-left:3px solid #1769D5;background-color:#F2F6FC;">'
                f'<tr><td style="padding:14px 16px;"><div style="{LABEL_STYLE}color:#1769D5;">{label}:</div>'
                f'<div style="{TEXT_STYLE}margin-top:6px;">{value}</div></td></tr></table>'
                '</td></tr>')
        elif block.kind == 'spacing':
            rows.append(f'<tr><td colspan="2" style="{TEXT_STYLE}padding:0;">{value}</td></tr>')
        else:
            # Introduction and signature remain in the exact configured position.
            rows.append(f'<tr><td colspan="2" style="{TEXT_STYLE}padding:12px 0;">{value}</td></tr>')
    flush_fields()
    content = ''.join(rows)
    # Visual event title only; the configured SMTP subject is never changed.
    heading = escape('Registro de activación' if title == 'Registro de activación FMS' else title, quote=True)
    # The same document is used by MIME and the isolated iframe preview. No
    # scripts, images, fonts, forms or network resources are permitted by CSP.
    return (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        'style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
        f'<title>Ticketyn — {heading}</title>'
        # Optional enhancement: clients without media queries retain the inline
        # two-column table layout. No CSS Grid or external styles are required.
        '<style>@media screen and (max-width:480px){'
        '.ticketyn-blocks,.ticketyn-blocks>tbody,.ticketyn-blocks>tbody>tr,.ticketyn-blocks>tbody>tr>td{display:block!important;width:100%!important;box-sizing:border-box;}'
        '.ticketyn-field{padding-right:0!important;}'
        '.ticketyn-blocks>tbody>tr>.ticketyn-empty{display:none!important;}'
        '.ticketyn-content{padding-left:20px!important;padding-right:20px!important;}'
        '}</style></head>'
        '<body style="margin:0;padding:0;background-color:#F0F2F5;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'bgcolor="#F0F2F5" style="width:100%;background-color:#F0F2F5;">'
        '<tr><td align="center" style="padding:20px 8px;">'
        '<!--[if mso]><table role="presentation" width="640" align="center" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'bgcolor="#FFFFFF" style="width:100%;max-width:640px;table-layout:fixed;background-color:#FFFFFF;">'
        '<tr><td bgcolor="#FFFFFF" class="ticketyn-content" style="padding:18px 28px;border-bottom:2px solid #1769D5;background-color:#FFFFFF;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;table-layout:fixed;">'
        '<tr><td align="left" style="font-family:Arial,Helvetica,sans-serif;font-size:24px;line-height:30px;font-weight:bold;color:#1769D5;">Ticketyn</td>'
        '<td align="right" style="font-family:Arial,Helvetica,sans-serif;font-size:10px;line-height:16px;letter-spacing:1px;color:#64748B;">OPERACIONES FMS</td></tr></table>'
        '</td></tr><tr><td class="ticketyn-content" style="padding:22px 28px 4px;">'
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:10px;line-height:16px;letter-spacing:1px;color:#64748B;">NOTIFICACIÓN OPERATIVA</div>'
        f'<h1 style="margin:6px 0 0;font-family:Arial,Helvetica,sans-serif;font-size:24px;line-height:30px;color:#17263C;">{heading}</h1>'
        '</td></tr><tr><td class="ticketyn-content" style="padding:0 28px 16px;">'
        '<table class="ticketyn-blocks" role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;table-layout:fixed;">'
        f'{content}</table></td></tr>'
        '<tr><td align="center" bgcolor="#F8FAFC" style="padding:14px 20px;background-color:#F8FAFC;font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:18px;color:#64748B;">Ticketyn · Gestión operativa</td></tr></table>'
        '<!--[if mso]></td></tr></table><![endif]-->'
        '</td></tr></table></body></html>')
