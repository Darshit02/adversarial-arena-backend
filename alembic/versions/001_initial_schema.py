"""Initial database schema for Adversarial Arena

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-30 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Organizations
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clerk_org_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_organizations_clerk_org_id", "organizations", ["clerk_org_id"], unique=True)
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    # 2. Users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("clerk_user_id", sa.String(128), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column("last_name", sa.String(128), nullable=True),
        sa.Column("role", sa.String(32), default="member", nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_clerk_user_id", "users", ["clerk_user_id"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_organization_id", "users", ["organization_id"])

    # 3. API Keys
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("hashed_key", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_api_keys_prefix", "api_keys", ["prefix"])
    op.create_index("ix_api_keys_org_id", "api_keys", ["organization_id"])

    # 4. Target Models
    op.create_table(
        "target_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model_identifier", sa.String(128), nullable=False),
        sa.Column("endpoint_url", sa.String(512), nullable=True),
        sa.Column("encrypted_api_key", sa.String(1024), nullable=True),
        sa.Column("default_temperature", sa.Float(), default=0.7, nullable=False),
        sa.Column("default_max_tokens", sa.Integer(), default=1024, nullable=False),
        sa.Column("is_whitebox", sa.Boolean(), default=False, nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_target_models_name", "target_models", ["name"])
    op.create_index("ix_target_models_organization_id", "target_models", ["organization_id"])

    # 5. Defense Configs
    op.create_table(
        "defense_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("defense_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parameters", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("priority", sa.Integer(), default=10, nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_defense_configs_name", "defense_configs", ["name"])
    op.create_index("ix_defense_configs_type", "defense_configs", ["defense_type"])
    op.create_index("ix_defense_configs_org_id", "defense_configs", ["organization_id"])

    # 6. Attack Templates
    op.create_table(
        "attack_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("attack_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("harm_category", sa.String(64), default="general", nullable=False),
        sa.Column("default_parameters", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("is_builtin", sa.Boolean(), default=False, nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_attack_templates_name", "attack_templates", ["name"])
    op.create_index("ix_attack_templates_type", "attack_templates", ["attack_type"])
    op.create_index("ix_attack_templates_org_id", "attack_templates", ["organization_id"])

    # 7. Runs
    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_model_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("target_models.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), default="pending", nullable=False),
        sa.Column("harm_category", sa.String(64), default="general", nullable=False),
        sa.Column("seed_prompts", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("attack_template_ids", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("defense_ids", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("metrics", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("report_url", sa.String(512), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_organization_id", "runs", ["organization_id"])
    op.create_index("ix_runs_target_model_id", "runs", ["target_model_id"])
    op.create_index("ix_runs_org_status_created", "runs", ["organization_id", "status", "created_at"])

    # 8. Attack Results
    op.create_table(
        "attack_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prompt_index", sa.Integer(), nullable=False),
        sa.Column("attack_type", sa.String(64), nullable=False),
        sa.Column("seed_prompt", sa.Text(), nullable=False),
        sa.Column("mutated_prompt", sa.Text(), nullable=False),
        sa.Column("target_response", sa.Text(), default="", nullable=False),
        sa.Column("defense_verdict", postgresql.JSONB(), server_default="{}", nullable=False),
        sa.Column("is_jailbroken", sa.Boolean(), default=False, nullable=False),
        sa.Column("jailbreak_score", sa.Float(), default=0.0, nullable=False),
        sa.Column("evaluation_reason", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Float(), default=0.0, nullable=False),
        sa.Column("tokens_used", sa.Integer(), default=0, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_attack_results_run_id", "attack_results", ["run_id"])
    op.create_index("ix_results_run_jailbroken", "attack_results", ["run_id", "is_jailbroken"])


def downgrade() -> None:
    op.drop_table("attack_results")
    op.drop_table("runs")
    op.drop_table("attack_templates")
    op.drop_table("defense_configs")
    op.drop_table("target_models")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.drop_table("organizations")
