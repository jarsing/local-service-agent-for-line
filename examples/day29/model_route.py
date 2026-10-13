"""Client configuration boundary, not a live migration test.

A factory is injected for offline tests. Production integration should pass
its version-pinned google.genai.Client factory. This module makes no calls.
"""
from dataclasses import dataclass
from typing import Callable, Any

@dataclass(frozen=True)
class ModelRoute:
    backend: str
    model: str
    project: str | None = None
    location: str | None = None


def make_client(route: ModelRoute, factory: Callable[..., Any], *,
                api_key: str | None = None, credentials: Any = None) -> Any:
    if not route.model or not route.model.strip():
        raise ValueError('MODEL_REQUIRED')
    if route.backend == 'developer':
        if not api_key or not api_key.strip() or route.project or route.location or credentials is not None:
            raise ValueError('DEVELOPER_CONFIG_CONFLICT')
        return factory(api_key=api_key.strip(), vertexai=False)
    if route.backend == 'vertex':
        if not route.project or not route.project.strip() or not route.location or not route.location.strip() or api_key or credentials is None:
            raise ValueError('VERTEX_CREDENTIALS_PROJECT_LOCATION_REQUIRED')
        return factory(vertexai=True, project=route.project.strip(),
                       location=route.location.strip(), credentials=credentials)
    raise ValueError('UNSUPPORTED_BACKEND')
