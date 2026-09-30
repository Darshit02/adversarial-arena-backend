"""Clerk Webhook receiver for automated User and Organization synchronization."""

from typing import Any
from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import AuthenticationError
from app.core.logging import get_logger
from app.core.security import verify_clerk_webhook_signature
from app.db.models.organization import Organization
from app.db.models.user import User
from app.dependencies import get_db

logger = get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/clerk", status_code=status.HTTP_200_OK)
async def clerk_webhook(
    request: Request,
    svix_id: str | None = Header(default=None, alias="svix-id"),
    svix_timestamp: str | None = Header(default=None, alias="svix-timestamp"),
    svix_signature: str | None = Header(default=None, alias="svix-signature"),
    session: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Verify incoming Clerk webhook payload via Svix headers and synchronize user/org entities."""
    settings = get_settings()
    body_bytes = await request.body()

    # In test mode or when secret is set to placeholder, bypass Svix header validation if headers absent
    if not (settings.is_test and not svix_id):
        headers = {
            "svix-id": svix_id or "",
            "svix-timestamp": svix_timestamp or "",
            "svix-signature": svix_signature or "",
        }
        event = verify_clerk_webhook_signature(
            payload_body=body_bytes,
            headers=headers,
            webhook_secret=settings.CLERK_WEBHOOK_SECRET,
        )
    else:
        import json
        event = json.loads(body_bytes.decode() or "{}")

    event_type = event.get("type", "")
    data = event.get("data", {})
    logger.info("Received Clerk webhook event", event_type=event_type)

    if event_type in ("user.created", "user.updated"):
        clerk_user_id = data.get("id")
        email_addresses = data.get("email_addresses", [])
        primary_email = email_addresses[0].get("email_address") if email_addresses else f"{clerk_user_id}@clerk.user"
        first_name = data.get("first_name")
        last_name = data.get("last_name")

        stmt = select(User).where(User.clerk_user_id == clerk_user_id)
        user = (await session.execute(stmt)).scalar_one_or_none()

        if not user:
            # Ensure a default organization exists
            org_stmt = select(Organization).limit(1)
            org = (await session.execute(org_stmt)).scalar_one_or_none()
            if not org:
                org = Organization(
                    clerk_org_id="org_default",
                    name="Default Research Org",
                    slug="default-org",
                )
                session.add(org)
                await session.flush()

            user = User(
                clerk_user_id=clerk_user_id,
                email=primary_email,
                first_name=first_name,
                last_name=last_name,
                role="member",
                organization_id=org.id,
            )
            session.add(user)
        else:
            user.email = primary_email
            user.first_name = first_name
            user.last_name = last_name

        await session.commit()

    elif event_type == "user.deleted":
        clerk_user_id = data.get("id")
        stmt = select(User).where(User.clerk_user_id == clerk_user_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if user:
            await session.delete(user)
            await session.commit()

    elif event_type in ("organization.created", "organization.updated"):
        clerk_org_id = data.get("id")
        name = data.get("name") or "Unnamed Organization"
        slug = data.get("slug") or f"org-{clerk_org_id[:8]}"

        stmt = select(Organization).where(Organization.clerk_org_id == clerk_org_id)
        org = (await session.execute(stmt)).scalar_one_or_none()
        if not org:
            org = Organization(clerk_org_id=clerk_org_id, name=name, slug=slug)
            session.add(org)
        else:
            org.name = name
            org.slug = slug

        await session.commit()

    return {"received": True}
