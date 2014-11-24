"""alter lac cid fields

Revision ID: c73eff4e86d
Revises: 1a116bcd0851
Create Date: 2014-11-20 21:44:40.347763

"""

# revision identifiers, used by Alembic.
revision = 'c73eff4e86d'
down_revision = '1a116bcd0851'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.execute('UPDATE cell SET cid = 0 WHERE cid < 0')
    op.execute('UPDATE cell SET lac = 0 WHERE lac < 0')

    op.execute('UPDATE cell_blacklist SET cid = 0 WHERE cid < 0')
    op.execute('UPDATE cell_blacklist SET lac = 0 WHERE lac < 0')

    op.execute('UPDATE cell_measure SET cid = 0 WHERE cid < 0')
    op.execute('UPDATE cell_measure SET lac = 0 WHERE lac < 0')

    op.execute('ALTER TABLE cell MODIFY cid INT UNSIGNED DEFAULT NULL')
    op.execute('ALTER TABLE cell_blacklist MODIFY cid INT UNSIGNED DEFAULT NULL')
    op.execute('ALTER TABLE cell_measure MODIFY cid INT UNSIGNED DEFAULT NULL')

    op.execute('ALTER TABLE cell MODIFY lac SMALLINT UNSIGNED DEFAULT NULL')
    op.execute('ALTER TABLE cell_blacklist MODIFY lac SMALLINT UNSIGNED DEFAULT NULL')
    op.execute('ALTER TABLE cell_measure MODIFY lac SMALLINT UNSIGNED DEFAULT NULL')


def downgrade():
    op.execute('ALTER TABLE cell MODIFY cid INT SIGNED DEFAULT NULL')
    op.execute('ALTER TABLE cell_blacklist MODIFY cid INT SIGNED DEFAULT NULL')
    op.execute('ALTER TABLE cell_measure MODIFY cid INT SIGNED DEFAULT NULL')

    op.execute('ALTER TABLE cell MODIFY lac INT SIGNED DEFAULT NULL')
    op.execute('ALTER TABLE cell_blacklist MODIFY lac INT SIGNED DEFAULT NULL')
    op.execute('ALTER TABLE cell_measure MODIFY lac INT SIGNED DEFAULT NULL')

    op.execute('UPDATE cell SET cid = -1 WHERE cid = 0')
    op.execute('UPDATE cell SET lac = -1 WHERE lac = 0')

    op.execute('UPDATE cell_blacklist SET cid = -1 WHERE cid = 0')
    op.execute('UPDATE cell_blacklist SET lac = -1 WHERE lac = 0')

    op.execute('UPDATE cell_measure SET cid = -1 WHERE cid = 0')
    op.execute('UPDATE cell_measure SET lac = -1 WHERE lac = 0')
