# Security policy

## Report privately

Use GitHub's private vulnerability reporting for this repository when available. If it is disabled, contact a repository maintainer through an established private channel. Include the affected version or commit, the affected component, prerequisites, impact and steps to reproduce with synthetic data. Keep credentials, customer information and exploit details out of public issues.

## Scope

The repository includes IAM, Operational, Agent Core, both Angular apps, a transactional email gateway and a local Compose topology. External provider accounts and independently deployed adapters have their own disclosure channels.

Reviewers should pay particular attention to JWT and tenant isolation, public contact and ingest inputs, signing key and internal credential handling, outbound provider traffic, and authentication, sender scoping and idempotency at the email gateway. The optional external adapter owns channel-specific signature validation and consent.

A usable report can describe a reachable boundary failure, affected data or actions, and required access. No additional risks are accepted here. See the [release review](RELEASE_READINESS.md) for open questions about deployment and distribution.
