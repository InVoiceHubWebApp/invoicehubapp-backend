"""Create paid status column

Revision ID: 7456186fe18d
Revises: a1b868f525f4
Create Date: 2025-04-19 23:46:02.096792

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "7456186fe18d"
down_revision: Union[str, None] = "a1b868f525f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
