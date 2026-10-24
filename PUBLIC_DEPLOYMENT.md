## Publication preference (2026-10-22)

The user requires explicit confirmation before future public updates. The user approved this release on 2026-10-23 (Asia/Shanghai), and version 3 has now been published. Root `dist/` and the publishing checkout contain the approved AI comparisons, subscription and print ordering, upload separation, and on-canvas artwork editing with tap-outside deselection. Further edits should remain local until separately confirmed.

# POPOMO public deployment

- Public URL: https://popomo-case-studio.cchunpat.chatgpt.site
- Deployed on: 2026-10-23 (Asia/Shanghai)
- Audience: public, anyone with the URL
- Publishing checkout: `sites/popomo-public/`
- Current Site manifest: `sites/popomo-public/.openai/hosting.json`
- Site ID: `appgprj_6ad9f683eaf48191816080a89bc316de`
- Version: 3
- Source commit: `8b17090f5fbcc20d28db0d0222f340881656fc76`
- Deployment ID: `appgdep_6ada332a7f84819181e4862c91f7a764`
- Verified result: Sites deployment succeeded; 85 tests passed before packaging.

The root `.openai/hosting.json` retains the inaccessible previous Site identity. The user explicitly chose to create a new public Site in the current account. Future releases should reuse the ID and repository in `sites/popomo-public/`; do not create another Site or deploy to the old root identity.

This is an interactive prototype. AI samples are fixed assets; payment, refunds, queue and printing are simulated. Uploaded photos and custom QR pass snapshots remain browser-local. Publishing does not connect the AI model, payment service or physical printer.

Historical version 1 post-deployment verification limit: the browser navigated to the production URL and exposed the POPOMO title, but accessibility inspection timed out twice. An unauthenticated command-line HEAD request received Cloudflare HTTP 403. Sites confirms successful deployment and public audience; full live-page browser inspection was not completed.

Version 2: AI Studio is an always-visible highlighted card with three style samples, price, selection checkmarks and a direct upload button. Verified style selection and upload in the browser, 390px responsive layout without horizontal overflow, and module syntax. Sites deployment succeeded. Screenshots: `test-results/simple-v1/ai-studio-highlight.png` and `ai-studio-mobile.png`.

Version 3: Published all locally approved changes. Saved version ID: `appgprj_6ad9f683eaf48191816080a89bc316de~appgver_10397ad3d3d0819188a304d83b32e511`. Sites returned `succeeded` with the unchanged public URL. No production browser QA was needed beyond the successful native deployment result; latest interactions were verified locally.

## Additional test server (2026-10-23)

The approved v3 was also deployed at https://aicase.dinglh.cn on 106.52.24.221, with HTTPS and a domain-specific renewal task. See `deploy/test-server/README.md` for paths, verification and update/rollback guidance. The existing Sites publication remains available. Future public changes still require user confirmation.

## Test-server editor release (2026-10-23)

The user approved deploying the latest local version to their test server. Root `dist/` includes a 24-item graphic library, direct photo move/resize/rotate, inline-editable custom/template text with a right-side font/color toolbar, and validated/persisted overlay snapshots. These changes are now live at https://aicase.dinglh.cn, release `20261023-005609-editor`. All 127 uploaded files passed checksum verification before the atomic switch; public HTTPS checks for the homepage and key resources returned 200 with matching hashes. Production browser navigation timed out; local interaction checks and 88 tests passed. The Sites checkout and chatgpt.site deployment remain on v3. Further public changes require confirmation.

## Test-server model-first release (2026-10-23)

Phone model selection now appears before the preview and customization on desktop and mobile. It automatically collapses after a choice, showing the current model and a Change entry; saved selections start collapsed. An empty selection stays expanded. It remains a required control associated with the order form, and selection updates the preview. Local browser verification passed. The user approved this update and it is now deployed to https://aicase.dinglh.cn as release `20261023-010644-model-first`. All 127 files passed checksum verification before the atomic switch, and public HTTPS checks of the homepage and key files matched the local version. The Sites deployment remains unchanged.

## Collection retention (deployed to test server 2026-10-23)

Switching from Collection to Your photo now retains the selected template layers and their edited positions, sizes, rotations, text and styles. Custom collection layers are merged with the existing photo layers without duplicate IDs. Uploaded/replaced photos sit beneath these overlays. Template layouts are validated and persisted in photo order/print snapshots; old photo-only passes remain compatible. Local switching, refresh and inline template text editing were verified; all 91 tests pass. Deployed with the brand picker in test-server release `20261023-112004-brand-picker`.

## Brand and model picker (deployed to test server 2026-10-23)

The expanded phone picker now groups the supported catalog by brand, offers search within the brand, and displays models in a bounded scrolling list. Selecting a model saves it, updates the preview and collapses the picker. Review still requires a supported model. Existing catalog order and model IDs are unchanged. New filtering tests include a 201-model synthetic catalog; all 93 tests pass. Local preview service restarted and phone-catalog.js returns 200. Browser automation was unavailable; native Chrome fallback was interrupted by user activity, so visual verification and a new screenshot were not completed. The user approved deployment of this change and the preceding collection-retention change to https://aicase.dinglh.cn. Release `20261023-112004-brand-picker` is active. All 128 files passed checksum verification before atomic activation; homepage and key scripts/styles returned HTTPS 200 with matching hashes. The previous release remains available for rollback. Sites remains unchanged.

## Explicit artwork deletion (deployed to test server 2026-10-23)

A labeled Delete button appears at the top-right of the preview for a selected template layer or added graphic/text. Delete/Backspace removes the selected layer outside text fields, while inline text editing retains normal character deletion. Template deletions persist as validated tombstones across refresh, photo mode, checkout and printing; deleting a copied custom overlay removes its matching ID from both source drafts to prevent reappearance. Button deletion, Backspace/Delete shortcuts, inline text safety and reload persistence were checked in an isolated localhost draft. All 95 tests pass. Screenshot: test-results/simple-v1/delete-artwork-button.png. The user approved deployment to https://aicase.dinglh.cn; release `20261023-135340-delete-artwork` is active. All 128 files passed checksum verification before atomic activation. Public HTTPS checks of the homepage and five key scripts/styles returned 200 with matching local hashes. The preceding brand-picker release is retained for rollback; Sites is unchanged.

## Pending local backend foundation (2026-10-23)

Frontend source moved to `frontend/storefront/`; original rule tests moved to `frontend/tests/`. Added independent Vue/Element Plus admin in `frontend/admin/` and Django REST API/database/RBAC in `backend/`. This is local only. Current test-server and Sites releases are unchanged. Managed configuration is not yet consumed by the storefront; real payment, AI workers and printer integration remain out of scope for this foundation.

## Test-server fullstack management release (2026-10-23)

User approved deployment of the backend foundation. Release `20261023-153023-admin` is live at https://aicase.dinglh.cn/admin/ with independent Django/Gunicorn, PostgreSQL, persistent public media and daily backups. Original storefront remains at `/`. All 133 web files and 20 backend files verified; live HTTPS login, CSRF, readonly RBAC, CRUD and uploads passed. Previous static release retained. Local credentials are in ignored `backend/.test-server-admin.txt`; no credentials in public files. The storefront still uses its existing static/browser data and does not consume managed configuration. Sites is unchanged.

## Test-server catalog integration release (2026-10-23)

Published `20261023-193732-catalog` to aicase.dinglh.cn. Backend-managed prices, quotas, styles and 4 original-to-multiple-effect examples now drive the storefront on reload. Admin has AI 案例 editing. 102 frontend / 23 backend tests pass; server manifests, public catalog, image URLs, admin authentication and case listing verified. See `deploy/test-server/README.md` for backup and rollback. Sites remains on its previous independent snapshot.
