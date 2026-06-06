# rules Path Override

## Purpose

This path defines rule taxonomy, vague-term policy, lifecycle boundaries, and
minimum information requirements.

## Rules

- Treat these JSON files as policy, not generated data.
- A rule may become deterministic only if it is explicit, schema-grounded, and
  type/operator safe.
- Vague terms must default to candidate, external-info-needed, or
  non-executable handling.
- If a term is moved from candidate to deterministic, add or update tests and
  explain why the value boundary is explicit.
- Do not add policies that allow unsupported fields to execute.

## Verification

Run JSON validation after editing:

```bash
python3 -m json.tool rules/rule_taxonomy.json >/dev/null
python3 -m json.tool rules/vague_terms.json >/dev/null
python3 -m json.tool rules/information_requirements.json >/dev/null
python3 -m unittest tests.test_rule_verifier
```

