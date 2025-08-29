"""add_model_constraints_and_validations

Revision ID: ea6eeb68b37b
Revises: 67ffd44bb76c
Create Date: 2025-02-11 14:04:13.459225

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ea6eeb68b37b'
down_revision: Union[str, None] = '67ffd44bb76c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # First handle existing data
    op.execute("UPDATE owners SET name = 'Unknown' WHERE name IS NULL")
    op.execute("UPDATE owners SET source = 'unknown' WHERE source IS NULL")
    op.execute("UPDATE owners SET external_id = 'unknown' WHERE external_id IS NULL")
    op.execute("UPDATE owners SET created_at = NOW() WHERE created_at IS NULL")
    op.execute("UPDATE owners SET updated_at = NOW() WHERE updated_at IS NULL")

    op.execute("UPDATE listings SET source = 'unknown' WHERE source IS NULL")
    op.execute("UPDATE listings SET external_id = 'unknown' WHERE external_id IS NULL")
    op.execute("UPDATE listings SET title = 'Unknown' WHERE title IS NULL")
    op.execute("UPDATE listings SET price = 0 WHERE price IS NULL")
    op.execute("UPDATE listings SET posted_date = NOW() WHERE posted_date IS NULL")
    op.execute("UPDATE listings SET processed_date = NOW() WHERE processed_date IS NULL")
    op.execute("UPDATE listings SET url = CONCAT('unknown_', id) WHERE url IS NULL")
    op.execute("UPDATE listings SET status = 'active' WHERE status IS NULL")
    op.execute("UPDATE listings SET created_at = NOW() WHERE created_at IS NULL")
    op.execute("UPDATE listings SET updated_at = NOW() WHERE updated_at IS NULL")

    op.execute("UPDATE listing_history SET price = 0 WHERE price IS NULL")
    op.execute("UPDATE listing_history SET changed_date = NOW() WHERE changed_date IS NULL")
    op.execute("UPDATE listing_history SET change_type = 'NEW' WHERE change_type IS NULL")
    op.execute("UPDATE listing_history SET created_at = NOW() WHERE created_at IS NULL")

    # Then add the constraints
    op.alter_column('listing_history', 'listing_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('listing_history', 'price',
               existing_type=sa.NUMERIC(),
               nullable=False)
    op.alter_column('listing_history', 'changed_date',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.alter_column('listing_history', 'change_type',
               existing_type=sa.VARCHAR(length=50),
               nullable=False)
    op.alter_column('listing_history', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    
    # Update foreign key constraints
    op.drop_constraint('listing_history_listing_id_fkey', 'listing_history', type_='foreignkey')
    op.create_foreign_key(None, 'listing_history', 'listings', ['listing_id'], ['id'], ondelete='CASCADE')
    
    # Add listings constraints
    op.alter_column('listings', 'owner_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('listings', 'source',
               existing_type=sa.VARCHAR(length=50),
               nullable=False)
    op.alter_column('listings', 'external_id',
               existing_type=sa.VARCHAR(length=100),
               nullable=False)
    op.alter_column('listings', 'title',
               existing_type=sa.TEXT(),
               nullable=False)
    op.alter_column('listings', 'price',
               existing_type=sa.NUMERIC(),
               nullable=False)
    op.alter_column('listings', 'posted_date',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.alter_column('listings', 'processed_date',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.alter_column('listings', 'url',
               existing_type=sa.TEXT(),
               nullable=False)
    op.alter_column('listings', 'status',
               existing_type=sa.VARCHAR(length=20),
               nullable=False)
    op.alter_column('listings', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.alter_column('listings', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    
    # Update listings foreign key
    op.drop_constraint('listings_owner_id_fkey', 'listings', type_='foreignkey')
    op.create_foreign_key(None, 'listings', 'owners', ['owner_id'], ['id'], ondelete='CASCADE')
    
    # Add owners constraints
    op.alter_column('owners', 'name',
               existing_type=sa.VARCHAR(length=100),
               nullable=False)
    op.alter_column('owners', 'source',
               existing_type=sa.VARCHAR(length=50),
               nullable=False)
    op.alter_column('owners', 'external_id',
               existing_type=sa.VARCHAR(length=100),
               nullable=False)
    op.alter_column('owners', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)
    op.alter_column('owners', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=False)


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('owners', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('owners', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('owners', 'external_id',
               existing_type=sa.VARCHAR(length=100),
               nullable=True)
    op.alter_column('owners', 'source',
               existing_type=sa.VARCHAR(length=50),
               nullable=True)
    op.alter_column('owners', 'name',
               existing_type=sa.VARCHAR(length=100),
               nullable=True)
    op.drop_constraint(None, 'listings', type_='foreignkey')
    op.create_foreign_key('listings_owner_id_fkey', 'listings', 'owners', ['owner_id'], ['id'])
    op.alter_column('listings', 'updated_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('listings', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('listings', 'status',
               existing_type=sa.VARCHAR(length=20),
               nullable=True)
    op.alter_column('listings', 'url',
               existing_type=sa.TEXT(),
               nullable=True)
    op.alter_column('listings', 'processed_date',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('listings', 'posted_date',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('listings', 'price',
               existing_type=sa.NUMERIC(),
               nullable=True)
    op.alter_column('listings', 'title',
               existing_type=sa.TEXT(),
               nullable=True)
    op.alter_column('listings', 'external_id',
               existing_type=sa.VARCHAR(length=100),
               nullable=True)
    op.alter_column('listings', 'source',
               existing_type=sa.VARCHAR(length=50),
               nullable=True)
    op.alter_column('listings', 'owner_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.drop_constraint(None, 'listing_history', type_='foreignkey')
    op.create_foreign_key('listing_history_listing_id_fkey', 'listing_history', 'listings', ['listing_id'], ['id'])
    op.alter_column('listing_history', 'created_at',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('listing_history', 'change_type',
               existing_type=sa.VARCHAR(length=50),
               nullable=True)
    op.alter_column('listing_history', 'changed_date',
               existing_type=postgresql.TIMESTAMP(),
               nullable=True)
    op.alter_column('listing_history', 'price',
               existing_type=sa.NUMERIC(),
               nullable=True)
    op.alter_column('listing_history', 'listing_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    # ### end Alembic commands ###
