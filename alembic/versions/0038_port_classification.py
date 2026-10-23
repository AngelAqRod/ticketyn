"""Guard optional port classification without changing historical rows."""
from alembic import op

revision = '0038_port_classification'
down_revision = '0037_port_nomenclatures'
branch_labels = None
depends_on = None

CLASSIFICATION_CHECK = """CASE WHEN nomenclature_id IS NULL THEN
    numbering_format IS NULL AND (number_components IS NULL OR number_components = 'null'::jsonb)
    ELSE numbering_format IS NOT NULL AND numbering_format IN ('N','X/Y','X/Y/Z','W/X/Y/Z')
    AND CASE WHEN jsonb_typeof(number_components) = 'array' THEN
        jsonb_array_length(number_components) = CASE numbering_format
            WHEN 'N' THEN 1 WHEN 'X/Y' THEN 2 WHEN 'X/Y/Z' THEN 3 WHEN 'W/X/Y/Z' THEN 4 END
        ELSE false END END"""


def upgrade():
    op.create_check_constraint('classification_complete', 'distribution_ports', CLASSIFICATION_CHECK)


def downgrade():
    op.drop_constraint(op.f('ck_distribution_ports_classification_complete'), 'distribution_ports', type_='check')
