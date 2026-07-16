"""Security policy for model providers used by gateway-owned conversations."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

_RuntimeT = TypeVar("_RuntimeT", bound=Mapping[str, Any])

_AGY_GATEWAY_BLOCK_MESSAGE = (
    "The agy provider is disabled for Hermes gateway sessions because its "
    "headless mode can auto-approve native tools. Use agy only from an explicitly "
    "approved isolated coding workspace until agy provides an enforceable no-tools mode."
)


class GatewayProviderPolicyError(RuntimeError):
    """Raised when a provider is unsafe for an unattended gateway session."""


def enforce_gateway_provider_policy(runtime: _RuntimeT) -> _RuntimeT:
    """Reject providers that can execute hidden native tools in gateway runs.

    Live agy 1.1.3 evidence shows ``--print --sandbox`` running Bash after an
    always-proceed confirmation. Gateway messages are untrusted remote input, so
    neither an ``agy`` alias nor a custom ``agy://`` route may reach AIAgent.
    The local provider remains available to explicitly approved coding workers.
    """
    from hermes_cli.runtime_provider import is_agy_process_route

    provider = runtime.get("provider")
    base_url = runtime.get("base_url")
    if not is_agy_process_route(
        str(provider) if provider is not None else None,
        base_url=str(base_url) if base_url is not None else None,
    ):
        return runtime

    logger.error(
        "Blocked unsafe gateway provider route: provider=%s route_type=agy",
        provider or "(unset)",
    )
    raise GatewayProviderPolicyError(_AGY_GATEWAY_BLOCK_MESSAGE)
