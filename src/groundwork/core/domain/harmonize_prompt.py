"""Render the user message of the agent: the request and the context, as delimited data.

Everything that came from outside (the draft, CRM fields, rules, passages) is JSON-encoded
inside a tag, and `<` and `>` are escaped, so a field that contains `</crm_data>` cannot
close its block and pose as an instruction. The system prompt tells the model that the
content of these blocks is data, never instructions.
"""

import json
from typing import Any

from groundwork.core.domain.harmonize import ContextPack, HarmonizeRequest

RULE_FIELDS = {"id", "kind", "statement", "scope", "product_ids", "claim_text"}


def render_user_message(context: ContextPack, request: HarmonizeRequest) -> str:
    asked = {"channel": request.channel, "contact_id": request.contact_id, "draft": request.draft}
    rules = [r.model_dump(mode="json", include=RULE_FIELDS) for r in context.rules]
    passages = [
        p.model_dump(mode="json", include={"chunk_id", "doc_id", "text"}) for p in context.passages
    ]
    blocks = [
        ("request", asked),
        ("crm_data", context.contact_context.model_dump(mode="json")),
        ("rules", rules),
        ("passages", passages),
    ]
    body = "\n".join(f"<{tag}>\n{_encode(value)}\n</{tag}>" for tag, value in blocks)
    return f"{body}\n\nWrite the email now."


def _encode(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e")
