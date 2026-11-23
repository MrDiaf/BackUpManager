# Milestone 06 — Local network access

## Objective

Use the UI from other machines on the home network without giving everyone on the LAN root access.

## Dependencies

Requires Milestones 01–05 (the running app and its docs).

## Existing-state check

Before making changes:

1. Inspect the relevant repository state.
2. Evaluate every completion criterion below and mark those already satisfied.
3. Run the smallest relevant verification when necessary.
4. If every criterion is satisfied, mark the milestone complete in this file and `PLAN.md` and make no implementation changes.
5. Otherwise preserve existing correct work and implement only what is missing.

Do not read other milestone files unless the repository cannot answer the question.

## Scope

`compose.yaml`, `Makefile`, `.env.example`, `app/web.py`, `app/main.py`, `tests/`, `README.md`.

## Required work

- Publish the port on all interfaces by default (`BIND_ADDRESS=0.0.0.0`).
- HTTP Basic auth on every request except `/health` (any username). The password comes from `UI_PASSWORD`, otherwise from `data/ui-password`, which is generated once at random (mode 0600). Compare with `hmac.compare_digest`.
- Keep the Origin/Referer check on POSTs (browsers attach cached Basic credentials to cross-site requests). Drop the `ALLOWED_HOSTS` Host check: with a password on every request it adds nothing, and it would need the LAN IP configured.
- `make up` prints the LAN URL. `make password` prints the password.
- README: document LAN access, the password, and that plain HTTP means the password travels unencrypted on the LAN.

## Completion criteria

- [x] The UI is reachable from other machines on the LAN at http://<host-ip>:8095
- [x] Every page except `/health` requires the password (401 without it)
- [x] A random password is generated on first start unless `UI_PASSWORD` is set; `make password` shows it
- [x] Cross-site POSTs are still refused, also with valid credentials

## Verification

`make test` (auth and Origin tests). `curl` the LAN IP with and without the password.
