"""Optional circuit site information: address, GPS point and additional notes."""
from alembic import op
import sqlalchemy as sa

revision = '0046_circuit_location'
down_revision = '0045_installation_order_types'
branch_labels = None
depends_on = None


def upgrade():
    # All columns are nullable and existing circuits keep NULL: no placeholder values.
    op.add_column('circuits', sa.Column('address', sa.Text()))
    op.add_column('circuits', sa.Column('latitude', sa.Numeric(9, 6)))
    op.add_column('circuits', sa.Column('longitude', sa.Numeric(9, 6)))
    op.add_column('circuits', sa.Column('additional_notes', sa.Text()))
    op.create_check_constraint(op.f('ck_circuits_gps_pair'), 'circuits', '(latitude IS NULL) = (longitude IS NULL)')
    op.create_check_constraint(op.f('ck_circuits_latitude_range'), 'circuits', 'latitude BETWEEN -90 AND 90')
    op.create_check_constraint(op.f('ck_circuits_longitude_range'), 'circuits', 'longitude BETWEEN -180 AND 180')


def downgrade():
    for name in ('ck_circuits_longitude_range', 'ck_circuits_latitude_range', 'ck_circuits_gps_pair'):
        op.drop_constraint(name, 'circuits')
    for column in ('additional_notes', 'longitude', 'latitude', 'address'):
        op.drop_column('circuits', column)
