"""Model arguments cannot set the mode, actor, session, revision or authority."""
from dataclasses import dataclass
from types import MappingProxyType

SAFE_FIELDS = MappingProxyType({
    "search_local_events": ("date", "area", "keyword"),
    "search_local_places": ("area", "dietary_type", "keyword"),
    "show_local_help": ("reason",),
})
SAFE_TOOLS = frozenset(SAFE_FIELDS)
POLICY_VERSION = "day16-read-only-v1"


class PermissionDenied(PermissionError):
    """A local authorization refusal, not a model opinion about an attack."""


@dataclass(frozen=True)
class ExecutionContext:
    tenant_id: str
    user_id: str
    session_id: str
    preference_revision: int
    mode: str = "untrusted_document"


class ReadPolicy:
    def __init__(self, memory, actor, session_id):
        self.memory, self.actor = memory, actor
        self.bound = ExecutionContext(
            actor.tenant_id, actor.user_id, session_id,
            memory.inspect(actor)["revision"]
        )

    # Teaching excerpt: exact source, no pseudo authority fields from the LLM.
    def authorize(self, name, args, context):
        if context != self.bound:
            raise PermissionDenied("CONTEXT_MISMATCH")
        if context.mode != "untrusted_document":
            raise PermissionDenied("DOCUMENT_MODE_REQUIRED")
        if name not in SAFE_TOOLS:
            raise PermissionDenied("TOOL_NOT_ALLOWED")
        if not isinstance(args, dict) or set(args) - set(SAFE_FIELDS[name]):
            raise PermissionDenied("UNEXPECTED_ARGUMENTS")
        if any(not isinstance(v, str) or len(v) > 100 for v in args.values()):
            raise PermissionDenied("INVALID_ARGUMENT_VALUE")
        normalized = {k: args.get(k, "") for k in SAFE_FIELDS[name]}
        if name == "search_local_places" and normalized["dietary_type"] not in (
            "", "any", "vegetarian", "vegan", "ovo_lacto"
        ):
            raise PermissionDenied("INVALID_DIETARY_VALUE")
        # Reads the original grants + preference row every time; no stale cache.
        try:
            self.memory.assert_revision(self.actor, context.preference_revision)
        except (PermissionError, RuntimeError) as exc:
            raise PermissionDenied("CURRENT_AUTHORITY_CHANGED") from exc
        return normalized

    def context_from_tool(self, tool_context):
        session = getattr(tool_context, "session", None)
        state = getattr(tool_context, "state", {})
        if session is None:
            raise PermissionDenied("TOOL_SESSION_REQUIRED")
        value = ExecutionContext(
            state.get("day16_tenant"), session.user_id, session.id,
            state.get("day16_preference_revision"), state.get("day16_mode")
        )
        if value != self.bound:
            raise PermissionDenied("TOOL_SESSION_MISMATCH")
        return value


def check_declarations(config):
    """Examine the actual pre-model config, not just a list of intended tools."""
    tools = config.get("tools", [])
    names = []
    for tool in tools:
        if not isinstance(tool, dict) or set(tool) - {
            "functionDeclarations", "function_declarations"
        }:
            raise PermissionDenied("UNAPPROVED_TOOL_KIND")
        declarations = tool.get("functionDeclarations", tool.get("function_declarations", []))
        for declaration in declarations:
            name = declaration.get("name")
            if name not in SAFE_TOOLS:
                raise PermissionDenied("PRIVILEGED_SCHEMA_EXPOSED")
            parameters = declaration.get("parameters", declaration.get("parametersJsonSchema", {}))
            properties = parameters.get("properties", {})
            if set(properties) != set(SAFE_FIELDS[name]):
                raise PermissionDenied("SCHEMA_ARGUMENT_MISMATCH")
            names.append(name)
    if len(names) != len(SAFE_TOOLS) or set(names) != SAFE_TOOLS:
        raise PermissionDenied("EXACT_READ_SCHEMA_REQUIRED")
    return tuple(names)
