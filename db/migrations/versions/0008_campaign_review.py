"""Add V2 campaign subjects to the existing Run, dependency and approval records."""
from alembic import op

revision = "0008_campaign_review"
down_revision = "0007_unused_reservations"
branch_labels = None
depends_on = None


def _check(table, name, column, kinds):
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {name}")
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({column} IN {kinds})")


def _apply(campaign):
    runs = ("scrape", "trends", "swot", "strategy", "calendar", "competitors",
            "poster", "social", "reel", "influencer_poster")
    approvals = ("swot", "strategy")
    relations = ("uses_trends", "uses_swot", "uses_strategy")
    if campaign:
        runs += ("campaign",)
        approvals += ("campaign",)
        relations += ("revises_campaign",)
    _check("runs", "ck_runs_kind_is_known", "kind", runs)
    _check("approvals", "ck_approvals_subject_kind_is_known", "subject_kind", approvals)
    _check("run_dependencies", "ck_run_dependencies_relation_is_known", "relation", relations)


def upgrade():
    _apply(True)


def downgrade():
    _apply(False)
