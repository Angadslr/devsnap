from __future__ import annotations

import os
from typing import Dict, Optional
from devsnap.config import ServiceConfig


def resolve_environment_variables(
    service_config: ServiceConfig,
    tunnel_urls: Dict[str, str],
    base_env: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Resolves injected variables like $services.<name>.tunnel_url into target environment."""
    env = (base_env or os.environ).copy()

    for target_key, template_val in service_config.inject_env.items():
        val = template_val
        for svc_name, url in tunnel_urls.items():
            token = f"$services.{svc_name}.tunnel_url"
            if token in val:
                val = val.replace(token, url)
        env[target_key] = val

    return env
