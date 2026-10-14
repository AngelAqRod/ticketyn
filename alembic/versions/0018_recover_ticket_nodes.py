"""Recuperar Nodos faltantes de tickets desde circuitos sin cambios históricos.

Requiere confirmar operativamente que el Nodo del circuito no cambió desde
0017. No infiere información para FMS ni sobrescribe referencias existentes.
"""
from alembic import op
import sqlalchemy as sa

revision = '0018_recover_ticket_nodes'
down_revision = '0017_historical_nodes'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # Serialize the evidence check and update against concurrent relation changes.
    bind.execute(sa.text('LOCK TABLE tickets, circuits, nodes IN SHARE ROW EXCLUSIVE MODE'))
    invalid = bind.scalar(sa.text('''
        SELECT count(*) FROM tickets t
        LEFT JOIN circuits c ON c.id = t.circuit_id
        LEFT JOIN nodes n ON n.id = c.node_id
        LEFT JOIN nodes recorded ON recorded.id = t.node_id
        WHERE (t.circuit_id IS NOT NULL AND c.id IS NULL)
           OR (c.node_id IS NOT NULL AND n.id IS NULL)
           OR (t.node_id IS NOT NULL AND recorded.id IS NULL)
    '''))
    if invalid:
        raise RuntimeError(f'Recuperación de Nodo cancelada: {invalid} relaciones ticket/circuito/Nodo inconsistentes. Revisar integridad antes de reintentar; no se asignaron Nodos.')
    bind.execute(sa.text('''
        UPDATE tickets AS t SET node_id = c.node_id
        FROM circuits AS c JOIN nodes AS n ON n.id = c.node_id
        WHERE t.circuit_id = c.id AND t.node_id IS NULL
    '''))


def downgrade():
    # No provenance ledger exists to distinguish recovered from operator-assigned
    # values. Retain truthful data rather than undoing it ambiguously.
    pass
