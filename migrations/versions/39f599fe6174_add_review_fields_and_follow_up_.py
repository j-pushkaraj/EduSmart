"""Add review fields and follow-up relationships

Revision ID: 39f599fe6174
Revises: cb464fbdab82
Create Date: 2025-10-13 18:36:52.669942
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '39f599fe6174'
down_revision = 'cb464fbdab82'
branch_labels = None
depends_on = None


def upgrade():
    # Add fields to followup_assignment
    with op.batch_alter_table('followup_assignment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('attempt_id', sa.Integer(), nullable=False))
        batch_op.add_column(sa.Column('student_answer', sa.String(length=1), nullable=True))
        # ✅ give the foreign key a name
        batch_op.create_foreign_key(
            'fk_followup_assignment_attempt_id',
            'test_attempt',
            ['attempt_id'],
            ['id']
        )

    # Add video_summary to recommended_video
    with op.batch_alter_table('recommended_video', schema=None) as batch_op:
        batch_op.add_column(sa.Column('video_summary', sa.Text(), nullable=True))

    # Add review-related fields to test_attempt
    with op.batch_alter_table('test_attempt', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reviewed', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('review_completed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('followup_score', sa.Float(), nullable=True))


def downgrade():
    # Remove review-related fields from test_attempt
    with op.batch_alter_table('test_attempt', schema=None) as batch_op:
        batch_op.drop_column('followup_score')
        batch_op.drop_column('review_completed_at')
        batch_op.drop_column('reviewed')

    # Remove video_summary from recommended_video
    with op.batch_alter_table('recommended_video', schema=None) as batch_op:
        batch_op.drop_column('video_summary')

    # Remove fields from followup_assignment
    with op.batch_alter_table('followup_assignment', schema=None) as batch_op:
        batch_op.drop_constraint('fk_followup_assignment_attempt_id', type_='foreignkey')
        batch_op.drop_column('student_answer')
        batch_op.drop_column('attempt_id')
