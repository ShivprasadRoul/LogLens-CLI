# Skills System

Skills are the mechanism by which LogLens understands the **domain** of your logs. A skill is a `.toml` file that gives the LLM two things:

1. **Domain context** — what the fields mean, what thresholds matter, what to focus on.
2. **JQ hints** — how to query specific fields in this log format.

---

## How Auto-Detection Works

When you run `loglens ingest` or `loglens chat`, LogLens:

1. Reads the discovered schema (field names and types)
2. Scores every built-in skill against the schema using a signal-matching algorithm
3. Selects the best-matching skill — or **blends multiple skills** if the log is hybrid

**Blending example:** A log file containing both `response_status` (HTTP) and `logger` (app) fields will activate **both** `nginx_access` and `app_logs`, merging their context and JQ hints.

You can see which skill was selected in the footer of every answer:
```
2 retrieval passes  ·  model: gpt-4o  ·  skill: nginx_access+app_logs
```

Force a specific skill with:
```bash
loglens chat my-app --skill nginx_access
```

---

## Managing Skills

### `loglens skills list`
Show all available skills and which one is auto-detected for a session.

### `loglens skills show <name>`
See exactly what domain knowledge a skill provides.
```bash
loglens skills show nginx_access
```

### `loglens skills add <file>`
Install a custom skill from a `.toml` file.
```bash
loglens skills add my_billing_skill.toml
```

### `loglens skills remove <name>`
Delete a user-installed skill.
```bash
loglens skills remove my_billing_skill
```

---

## Writing a Custom Skill

Create a `.toml` file anywhere:

```toml
[meta]
name        = "billing_service"
description = "Billing and payment processing logs"
version     = "1.0"

[detection]
# Field names in your logs that identify this skill
signals = ["billing_id", "stripe_customer_id", "invoice_status", "payment_method"]

[prompts]
domain_context = """
DOMAIN: Billing Service Logs.

Key fields:
- invoice_status: "paid" | "failed" | "pending" | "refunded"
- payment_method: "card" | "upi" | "netbanking"
- billing_id: unique invoice identifier (UUID)
- stripe_customer_id: Stripe customer reference

IMPORTANT THRESHOLDS:
- Failure rate > 2%: CRITICAL — alert immediately
- Failure rate 1-2%: WARNING
- p95 payment latency > 3000ms: investigate

Common failure patterns:
- "card_declined" in message → card issue, not code bug
- "webhook_timeout" → Stripe webhook delivery problem
"""

jq_hints = """
- Invoice ID field: .billing_id
- Status filter: select(.invoice_status == "failed")
- Payment method: .payment_method
- Failure rate: count failed vs total per .payment_method
- Latency: .processing_time_ms
"""
```

Install it:
```bash
loglens skills add billing_service.toml
```

This copies it to `~/.loglens/skills/billing_service.toml`. It will now auto-detect when your logs contain `billing_id` or `stripe_customer_id`.

---

## Custom Skill Tips

- **signals**: These are the field names that trigger the skill. Be specific — don't use common fields like `timestamp` or `level` that appear in every log.
- **domain_context**: Think of this as briefing a junior analyst. Explain the business domain, field semantics, and what "bad" looks like.
- **jq_hints**: Give concrete examples of how to filter and extract your most important fields. The LLM uses these to generate better JQ programs.
- **Blending**: Your custom skill will automatically blend with built-in skills if both score above the threshold. You don't need to duplicate nginx or app_logs context.

---

## Skill File Location

LogLens looks for skills in this order:

1. Built-in skills bundled with the install (`~/.loglens/install/skills/`)
2. User-installed skills (`~/.loglens/skills/`)

User-installed skills always take priority and can override built-ins of the same name.
