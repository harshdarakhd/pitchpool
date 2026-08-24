"""Add quiz_questions.kind so auto-generated quizzes can self-score."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_quiz_kind"
down_revision: Union[str, None] = "001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("quiz_questions")]
    if "kind" not in columns:
        op.add_column(
            "quiz_questions",
            sa.Column("kind", sa.String(length=32), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("quiz_questions", "kind")
