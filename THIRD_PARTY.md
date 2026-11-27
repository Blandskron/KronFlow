# Third-party components

The root Apache-2.0 license covers original KronFlow work. Dependencies and base images retain their own terms. This file identifies components to review for a distribution; it is not a complete notice bundle for a container image.

| Component | Evidence | License recorded upstream or in the lockfile |
| --- | --- | --- |
| Baileys | [Connector package manifest](backend/baileys-services/package.json), [upstream](https://github.com/WhiskeySockets/Baileys) | MIT |
| libsignal, bundled by the connector | [Connector lockfile](backend/baileys-services/package-lock.json), [upstream](https://github.com/WhiskeySockets/libsignal-node/blob/master/LICENSE) | GPL-3.0 |
| Sharp/libvips packages | [Connector lockfile](backend/baileys-services/package-lock.json), optional platform packages | Includes LGPL-3.0-or-later; exact files vary by platform |
| Frontend packages | [CRM lockfile](frontend/app/package-lock.json), [landing lockfile](frontend/landing/package-lock.json) | Angular production builds generate bundled license notices |

The connector Dockerfile copies production `node_modules` into the final image. A source release need not include any prebuilt images. Keep the connector image out of the published release until its actual platform dependencies, notices and any corresponding-source obligations have been reviewed. Also review base image packages, Python dependency licenses and rights to any separately distributed brand assets.

For every push and pull request, `.github/workflows/validate.yml` automatically generates and uploads CycloneDX SBOM artifacts (`npm sbom --package-lock-only --sbom-format cyclonedx`) for `frontend/app`, `frontend/landing`, and `backend/baileys-services` (`PRV-027`). For a release candidate, verify the generated SBOM artifacts against the images and bundles actually being shipped; lockfile inventories do not include OS packages or prove which optional component was installed. Keep the resulting license files and release material together.
