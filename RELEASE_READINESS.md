# Release readiness

**Status** · Initial Flowkron source distribution.

## Repository and dependencies

The repository contains two Angular SPAs, Django IAM, Operational and Agent Core on FastAPI, the Blandskron mail gateway, contracts and Docker Compose. Postgres and Redis are local services. Groq and Resend are configured separately. Meta credentials and webhook handling belong to an external WhatsApp adapter.

The Python manifests use PyPI packages and the Angular lockfiles resolve to npm registry packages. No private package registry is required by the integrated stack. Flowkron is distributed by BLANDSKRON under Apache-2.0. Third-party packages retain their own license and attribution terms. The brand artwork follows the palette and requirements supplied in the brief. The separate Blandskron Brand Guidelines v1.0 was unavailable for review.

## Secrets and data

- Gitleaks 8.30.1 scanned the locally reachable Git history across refs. It found no recognized secret patterns in the single available commit.
- A separate scan of the proposed change was run using a temporary Git index. The final staged-content scan reported no matches. Example mail keys and idempotency values are synthetic. Service configuration, keys, local databases and other generated data are excluded by ignore rules.
- Development examples use reserved addresses, synthetic lead records and non-routable numbers. The sample mail backend logs messages to the IAM console, which is suitable for synthetic local data only.
- Pattern scanning may miss custom credentials or personal data. Review the specific archive intended for publication, including any assets, history and database fixtures.

## Validated locally

- Both Angular applications built. The CRM reports a pre-existing style budget warning for the business-context page.
- IAM passed 23 tests, including the HTTP mail backend. Agent Core and the gateway passed 10 tests each. Operational imported and generated its OpenAPI document. The synthetic seed ran against a disposable PostgreSQL schema, which the validation script rolled back.
- Ruff syntax and undefined-name checks, the three contract validators and Docker Compose configuration passed.
- Python dependency audits reported no known vulnerabilities after the dependency updates. Both Angular production dependency audits reported zero findings. A full npm audit of the shared dependency tree reported 21 moderate development-toolchain findings and zero high or critical findings.

- Docker Compose brought all eight services to healthy in an isolated project. Chromium verified the landing and login in both themes at desktop and mobile widths, submitted the real contact form and opened the dashboard and access page with a synthetic signed-in account. Both apps served the favicon and manifest.
- A local provider mock verified Django → HTTP gateway → Resend request construction for a multipart message.

## Release gaps

- Review the privacy and terms text for each hosted deployment, and configure a monitored vulnerability reporting channel.
- Verify Resend delivery with tenant-owned test sender credentials. Verify any WhatsApp adapter with approved Meta test credentials, including webhook signature, consent, reply delivery, handoff and retry behavior. The stack still needs an external adapter to provide those channel flows.
- Assess platform-specific production hardening, existing authorization gaps and remaining development dependency advisories before a public release.
