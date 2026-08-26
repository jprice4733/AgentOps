"""Per-(conversation, call_id) asyncio.Future registry for tool permission gating.

**Architecture decision — tool-call approval, not user RBAC:**
This module implements per-tool-call approval: the agent *asks* before running
a mutating tool, the user clicks Allow/Deny in the UI, and the Future is
resolved.  This is NOT user authentication or authorization — there is no
concept of which user is allowed to do what.  Access to the webapp itself is
controlled by DSS (who can open the project); everyone who can open it shares
the same capability level.

When real per-user authorization is needed (e.g. admin vs read-only users,
multi-tenant data isolation), the right approach is:
  1. Resolve the DSS user via ``dataiku.api_client().get_auth_info()``.
  2. Map the user/group to a role (stored in project variables or a dataset).
  3. Check the role in a FastAPI dependency injected into each route.
This design is intentionally absent here to keep the starter simple.

See README.md "Architecture decisions" for the full trade-off discussion.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)


@dataclass
class PermissionResult:
    decision: Literal["allow", "deny"]
    remember: bool = False


class PermissionBroker:
    def __init__(self) -> None:
        self._pending: dict[tuple[str, str], asyncio.Future[PermissionResult]] = {}

    def create_pending(
        self, conversation_id: str, call_id: str
    ) -> asyncio.Future[PermissionResult]:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[PermissionResult] = loop.create_future()
        self._pending[(conversation_id, call_id)] = fut
        return fut

    def resolve(
        self,
        conversation_id: str,
        call_id: str,
        decision: Literal["allow", "deny"],
        remember: bool = False,
    ) -> bool:
        fut = self._pending.pop((conversation_id, call_id), None)
        if fut is None or fut.done():
            return False
        fut.set_result(PermissionResult(decision=decision, remember=remember))
        return True

    def cancel_for_conversation(self, conversation_id: str) -> None:
        to_cancel = [k for k in list(self._pending) if k[0] == conversation_id]
        for key in to_cancel:
            fut = self._pending.pop(key, None)
            if fut and not fut.done():
                fut.cancel()
                logger.info("Cancelled pending permission %s/%s", *key)


broker = PermissionBroker()
