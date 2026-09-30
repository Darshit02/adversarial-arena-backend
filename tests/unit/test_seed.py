"""Unit tests for the idempotent database seeding script."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models.organization import Organization
from app.db.models.user import User
from scripts.seed import seed


@pytest.mark.asyncio
async def test_seed_fresh_database():
    """Verify seed() creates all default entities when run on a blank database."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.add_all = MagicMock()

    mock_session_context = AsyncMock()
    mock_session_context.__aenter__.return_value = mock_session
    mock_session_context.__aexit__.return_value = None

    with patch("scripts.seed.async_session_factory", return_value=mock_session_context):
        await seed()

    # Verify entities added
    assert mock_session.add.call_count >= 10  # org, user, 4 probes, 3 validators, 2 targets, 1 run
    assert mock_session.add_all.call_count == 1  # 4 attack results
    assert mock_session.commit.call_count >= 2


@pytest.mark.asyncio
async def test_seed_idempotent_existing_database():
    """Verify seed() does not recreate existing records when run repeatedly."""
    dummy_org = Organization(
        id=uuid.uuid4(),
        clerk_org_id="org_acme_research",
        name="Acme Research",
        slug="acme-research",
    )
    dummy_user = User(
        id=uuid.uuid4(),
        clerk_user_id="user_acme_researcher",
        email="researcher@acme.ai",
        first_name="Alice",
        last_name="Researcher",
        role="admin",
        organization_id=dummy_org.id,
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    # Alternate or return existing object (dummy_org or dummy_user)
    mock_result.scalar_one_or_none.side_effect = [
        dummy_org,
        dummy_user,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    ]
    mock_session.execute.return_value = mock_result
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.add_all = MagicMock()

    mock_session_context = AsyncMock()
    mock_session_context.__aenter__.return_value = mock_session
    mock_session_context.__aexit__.return_value = None

    with patch("scripts.seed.async_session_factory", return_value=mock_session_context):
        await seed()

    # In existing case, nothing new should be added to session
    assert mock_session.add.call_count == 0
    assert mock_session.add_all.call_count == 0
    assert mock_session.commit.call_count == 1
