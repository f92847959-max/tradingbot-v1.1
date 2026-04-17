"""add news_sentiment table (Phase 11)

Revision ID: 20260416_news_sent
Revises:
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa

revision = "20260416_news_sent"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_sentiment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("entry_id", sa.Text(), nullable=False),
        sa.Column("sentiment_score", sa.Numeric(5, 4), nullable=False),
        sa.Column(
            "source_weight",
            sa.Numeric(4, 3),
            nullable=False,
            server_default="1.0",
        ),
        sa.Column("keywords_matched", sa.JSON(), nullable=True),
        sa.Column(
            "model_used",
            sa.String(20),
            nullable=False,
            server_default="vader",
        ),
    )
    op.create_index(
        "idx_news_sentiment_published", "news_sentiment", ["published_at"]
    )
    op.create_index(
        "idx_news_sentiment_source", "news_sentiment", ["source"]
    )
    op.create_index(
        "uq_news_sentiment_entry_id",
        "news_sentiment",
        ["entry_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_news_sentiment_entry_id", table_name="news_sentiment")
    op.drop_index("idx_news_sentiment_source", table_name="news_sentiment")
    op.drop_index("idx_news_sentiment_published", table_name="news_sentiment")
    op.drop_table("news_sentiment")
