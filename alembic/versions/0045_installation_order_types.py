"""Permanent NORMAL / EXTRAORDINARY modality for installation orders."""
from alembic import op
import sqlalchemy as sa

revision = '0045_installation_order_types'
down_revision = '0044_admin_requests'
branch_labels = None
depends_on = None

SHAPE = """order_type IS NULL OR (order_type = 'NORMAL' AND circuit_id IS NOT NULL AND description IS NULL
    AND service_type_id IS NULL AND node_id IS NULL AND sector_id IS NULL)
    OR (order_type = 'EXTRAORDINARY' AND circuit_id IS NULL AND description IS NOT NULL
    AND service_type_id IS NOT NULL AND node_id IS NOT NULL AND sector_id IS NOT NULL)"""


def upgrade():
    op.add_column('installation_orders', sa.Column('order_type', sa.String(20)))
    op.add_column('installation_orders', sa.Column('description', sa.Text()))
    for column, table in (('service_type_id', 'service_types'), ('node_id', 'nodes'), ('sector_id', 'sectors')):
        op.add_column('installation_orders', sa.Column(column, sa.Integer(), sa.ForeignKey(table + '.id')))
        op.create_index(f'ix_installation_orders_{column}', 'installation_orders', [column])
    # Legacy free-text columns are preserved, only relaxed for new typed orders.
    op.alter_column('installation_orders', 'service', nullable=True)
    op.alter_column('installation_orders', 'location', nullable=True)
    # A linked order is unambiguously NORMAL; unlinked legacy orders stay unclassified (NULL).
    op.execute("UPDATE installation_orders SET order_type = 'NORMAL' WHERE circuit_id IS NOT NULL")
    op.create_check_constraint(op.f('ck_installation_orders_order_type_shape'), 'installation_orders', SHAPE)
    op.execute("""CREATE FUNCTION installation_order_type_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.order_type IS NOT NULL AND NEW.order_type IS DISTINCT FROM OLD.order_type THEN
                RAISE EXCEPTION 'installation order type is permanent' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER installation_order_type_immutable BEFORE UPDATE OF order_type ON installation_orders
        FOR EACH ROW EXECUTE FUNCTION installation_order_type_immutable()""")


def downgrade():
    # Typed orders cannot be represented by the previous schema without inventing service/location text.
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM installation_orders WHERE service IS NULL OR location IS NULL")):
        raise RuntimeError('Cannot downgrade: typed installation orders lack the legacy service/location text.')
    op.execute('DROP TRIGGER installation_order_type_immutable ON installation_orders')
    op.execute('DROP FUNCTION installation_order_type_immutable()')
    op.drop_constraint('ck_installation_orders_order_type_shape', 'installation_orders')
    op.alter_column('installation_orders', 'service', nullable=False)
    op.alter_column('installation_orders', 'location', nullable=False)
    for column in ('sector_id', 'node_id', 'service_type_id'):
        op.drop_index(f'ix_installation_orders_{column}', 'installation_orders')
        op.drop_column('installation_orders', column)
    op.drop_column('installation_orders', 'description')
    op.drop_column('installation_orders', 'order_type')
