# Test server deployment

## Current prompt settings release (2026-10-27)

Web and backend now use `20261027-002200-prompts`. The admin page is https://aicase.dinglh.cn/admin/ai-prompts . Previous web release `20261026-004635-draft-session` and backend release `20261025-235321-images` are retained for rollback. Database/media/config backup completed at `/var/backups/aicase/data-20261026T162108Z` before migration 0004.

This release adds independent style and per-model prompt management, reusable templates, combined preview/copy, and unsaved-change protection. The new model prompt is private to authorized admin APIs. Existing configured prompts, prices, cases, orders, role grants, and storefront assets are preserved. No real image-generation API is connected.

Verification: 111 storefront tests and 44 backend tests pass; production admin build, migration consistency and Django checks pass. Local browser verification covers editing, template fill, persistence after reload, model/style combination and discard protection. Public HTTPS verified every admin build file against local hashes, confirmed unchanged storefront JavaScript, anonymous denial, authenticated prompt read/write/clear and public catalog privacy. Disposable inactive style/model records used for live checks were removed; audit logs remain. Backend health and service activation passed.

Rollback: switch web and backend symlinks to the previous releases and restart `aicase-backend`. Retain the additive migration and saved data; do not reverse the migration or restore local SQLite onto the server.

Deployed 2026-10-23 (Asia/Shanghai) with the user's approval.

- URL: https://aicase.dinglh.cn
- Server: 106.52.24.221, SSH root using the existing local key and verified known-host entry.
- Release: `/www/wwwroot/aicase.dinglh.cn/releases/20261023-193732-catalog`
- Active root: `/www/wwwroot/aicase.dinglh.cn/current` (symlink to release).
- Source: approved `frontend/storefront/` plus the built `frontend/admin/dist/` under `/admin/`. The independent Python backend is deployed outside the web root. Sites remains on v3.
- Previous release retained for rollback: `/www/wwwroot/aicase.dinglh.cn/releases/20261023-135340-delete-artwork` (earlier releases also retained).
- Nginx config: `/www/server/panel/vhost/nginx/aicase.dinglh.cn.conf`.
- Logs: `/www/wwwlogs/aicase.dinglh.cn.log` and `.error.log`.
- HTTP redirects to HTTPS; HTTP ACME challenges remain accessible.
- Certificate: `/www/server/panel/vhost/letsencrypt/aicase.dinglh.cn/`, issued using the server's existing BaoTa ACME client/account. Private key remains on the server, mode 600.
- Certificate expires 2027-01-20 23:19:06 Asia/Shanghai.
- Renewal: `/etc/cron.d/aicase-ssl` runs `/usr/local/sbin/renew-aicase-ssl` daily at 04:23 in the server timezone. It takes an exclusive lock, skips certificates with over 30 days remaining, issues for this domain only, validates the new certificate and Nginx configuration, then reloads Nginx. Log: `/www/wwwlogs/aicase-ssl-renew.log`.
- This virtual host is managed directly through its config file; no BaoTa site database record was added.

Verification: `nginx -t` passed, cron daemon active, renewal's non-expiring skip path passed, HTTPS certificate validation and homepage returned HTTP 200, HTTP returned a 301 redirect to HTTPS, AI example image returned 200. Served `simple-app.js` SHA-256 matched the approved local file (`a6efd68154a0c69e5d9c9cee30d9a8b8dba59a13ea06b4bd8e105ec0afea178a`). Browser inventory showed the POPOMO page title; automation inspection timed out, so no fresh production interaction test was completed. The same static version passed 85 tests and interaction checks before its original publication.

Future releases: obtain user approval, upload only the approved static `dist/` files into a new release directory, verify contents, then atomically replace the `current` symlink. Keep earlier releases for rollback; rollback by switching the symlink to a retained release. No Node process or build is required in production. Keep the challenge directory outside releases so certificate renewals survive release switches.

The app is still a prototype: AI, payments and printer actions are simulated, with drafts and orders stored per browser origin. Data from localhost or the chatgpt.site domain does not transfer automatically to this domain.

## Editor release verification (2026-10-23)

Uploaded static files into a fresh release and verified all 127 files against SHA-256 checksums before atomically switching `current`. HTTPS returned 200 with matching local hashes for the homepage, simple-app.js, simple.css, simple-personalize.js, editor-model.js, artwork-drag.js and two SVG graphic assets. Local interaction checks and all 88 tests passed before deployment. Production browser navigation timed out, so fresh visual verification was unavailable. Nginx and TLS configuration were unchanged. The release includes `SHA256SUMS` for auditing.

## Model-first release (2026-10-23)

User approved deployment of model selection before the editor, with automatic collapse after selection and a compact current-model/Change row. All 127 static files passed SHA-256 verification before atomic activation. Public HTTPS checks returned 200 and matched local bytes for index.html, simple-app.js, simple.css, simple-personalize.js and editor-model.js. The selection, auto-collapse and reopen behavior was verified locally before release; no new production browser inspection was attempted after the earlier automation timeouts.

## Brand picker and collection-retention release (2026-10-23)

User approved deployment of all pending changes: brand → model selection with search and auto-collapse, plus retention of collection template layers/custom graphics when switching to uploaded photos. Release `20261023-112004-brand-picker` contains 128 static files verified with SHA-256 before atomic activation. Public HTTPS checks returned 200 with matching hashes for index.html, simple-app.js, simple.css, simple-personalize.js, phone-catalog.js and editor-model.js. All 93 tests passed before deployment. Visual verification of the brand picker remains unavailable due to the previously reported browser connection issue; no production browser verification was claimed.

## Artwork deletion release (2026-10-23)

User approved release `20261023-135340-delete-artwork`, adding a visible Delete button for selected template and custom graphic/text layers and Delete/Backspace shortcuts outside text fields. All 128 static files passed SHA-256 verification before atomic activation. Public HTTPS checks returned 200 with matching local hashes for index.html, simple-app.js, simple.css, simple-personalize.js, art.js and phone-catalog.js. All 95 tests and local deletion, inline text safety and persistence checks passed before deployment. The previous release is retained for rollback. No fresh production browser interaction check was performed. Nginx, TLS and Sites were unchanged.

## Local module restructuring (not deployed)

The root static source moved from `dist/` to `frontend/storefront/`. Future static-only releases must package that directory. A separate Vue admin lives in `frontend/admin/`, and the Django API lives in `backend/`. Neither new module has been published. See `deploy/fullstack/README.md` for a future deployment plan; do not expose the project root or private backend files.

## Management backend deployed (2026-10-23)

User explicitly approved test-environment deployment. Release `20261023-153023-admin` is active.

- Admin URL: https://aicase.dinglh.cn/admin/
- User-facing editor: https://aicase.dinglh.cn/ (unchanged behavior).
- Web release contains original storefront at root and admin build under `admin/`; 133 files verified by SHA-256.
- Backend source: `/opt/aicase/releases/20261023-153023-admin`, symlink `/opt/aicase/current`; 20 source/dependency files verified.
- Virtualenv: `/opt/aicase/venvs/20261023-153023-admin`, Python 3.11.6, locked packages. `typing_extensions` is conditionally locked for Python < 3.13.
- Service: `aicase-backend.service`, enabled at boot, two Gunicorn workers on `127.0.0.1:18010`, unprivileged `aicase` user, read-only system paths and writable media directory. Logs: `journalctl -u aicase-backend`.
- Database: dedicated Docker container `aicase-postgres`, PostgreSQL 16 Alpine, restart unless-stopped, port `127.0.0.1:15432`, persistent `/var/lib/aicase/postgres`. Application role `aicase` owns only its database and has no superuser, CREATEDB or CREATEROLE privileges.
- Database image: `mirror.ccs.tencentyun.com/library/postgres@sha256:f4610795587492cd4fb887c2dc3de301b813278bb6f616992061141b5f15ac36` (Tencent mirror of the official image). The standard registry download was slow, so the mirror was used. Local tag `postgres:16-alpine` refers to this image.
- Environment: `/etc/aicase/backend.env` and `/etc/aicase/postgres.env`, root-only mode 600, outside web root. Production DEBUG disabled, secure cookies, trusted same-origin HTTPS proxy.
- Public library uploads: `/var/lib/aicase/media`, owned by the service user. `DJANGO_MEDIA_ROOT` decouples uploads from releases. User-uploaded editor photos remain browser-local.
- Initial independent test administrator: `admin`. Random credentials stored in root-only `/etc/aicase/admin-initial.txt`, copied to ignored local `backend/.test-server-admin.txt` mode 600. Credentials are not in this document or any static release.
- Nginx adds admin SPA fallback, API proxy, public media and per-IP login throttling (10/min with burst 5); original domain TLS and ACME configuration retained. `/admin/assets/` serves hashed bundles.
- Nginx pre-change backup: `/var/backups/aicase/nginx-before-20261023-153023-admin.conf`.
- Daily backup: `/etc/cron.d/aicase-backup`, 04:40 Asia/Shanghai, calls `/usr/local/sbin/aicase-backup`. Dumps PostgreSQL, archives media, and stores private environment/config plus release pointers. Root-only backups under `/var/backups/aicase/data-*`, about 7 days retention, exclusive lock. Log: `/var/log/aicase-backup.log`.
- First verified backup: `/var/backups/aicase/data-20261023T074324Z`. pg_restore list confirms expected catalog and account tables. This is a local-server backup, not off-site disaster recovery.

Verification: local 18 backend tests passed after persistent-media settings, admin production build passed; prior 95 storefront tests remain applicable because storefront files did not change. Both server manifests verified (153 files total); `pip check`, Nginx syntax and backend health passed. Public HTTPS homepage, editor assets, all admin bundles and `/admin/roles` match local hashes. Real administrator login, all 10 lists, database create/update/read/delete, Secure/HttpOnly cookies, missing-CSRF rejection, anonymous denial, hidden-file denial, readonly-role restrictions and image upload/serving passed. Disposable test account and image removed; audit trail retained. Both services are running and backend enabled at boot. Browser automation still returned transport closed, so no fresh visual QA is claimed.

Django deploy checks reported only HSTS subdomain/preload warnings. These flags remain disabled intentionally: this deployment does not authorize HSTS preload or policies for other subdomains.

Rollback: restore the saved Nginx config, switch the web `current` symlink back to `20261023-135340-delete-artwork`, validate Nginx, reload, and stop `aicase-backend` if reverting to static-only service. Preserve PostgreSQL, media, secrets and backups; do not delete them or run old migrations backwards. For future fullstack upgrades, back up before migrations, stage a separate backend/venv and web release, validate before switching pointers. Do not overwrite live data with local SQLite.

Backend configuration is not yet consumed by the storefront; this release does not activate real payment, AI generation or printing.

## Prices and multi-style examples deployed (2026-10-23 19:39 Asia/Shanghai)

Release `20261023-193732-catalog` is active for both the storefront/admin and backend. Previous pointers both refer to `20261023-153023-admin`. The existing locked virtualenv, database, service configuration and Nginx configuration are unchanged.

- Backed up database, media and private configuration before migration: `/var/backups/aicase/data-20261023T113904Z`.
- Migration `0002_aiexample_aiexampleresult_and_more` adds original/effect relationships and one-active-plan-per-kind constraint. Seeded 4 cases with 12 effects, preserving all existing plan values and role grants.
- Storefront reads catalog v2 on page load. Current configured values: print USD 9.90, AI USD 5.99/month, 15 monthly generations and 1 trial. Reload the storefront after saving configuration.
- Admin includes AI 案例: original image, subject, sort/enable, and multiple style/image rows. Existing non-superuser roles need explicit new case permissions; seed does not widen grants.
- New orders use current prices; saved print orders, AI sample results and current subscription-period entitlements retain snapshots. Trial counts support zero and multiple uses. On catalog failure new orders are unavailable, with a retry notice.
- 140 web files and 22 backend files passed server-side SHA-256 manifest verification. Six served storefront source hashes match local files; all 16 original/effect image URLs return 200 with matching lengths. Public catalog values, authenticated admin login and four case records pass. The existing 10-character administrator password works; the local private credential file has been synchronized.
- 102 storefront tests and 23 backend tests pass. Admin production build and Django/migration checks pass. Local browser checks cover 12 effect combinations, case edit/save/reload synchronization (temporary text restored), a USD 9.90 demo checkout and saved QR, plus a 390px viewport without horizontal overflow. Screenshots and machine-readable results are under `test-results/catalog-integration/`. The public site browser transport timed out, so no new public browser visual verification is claimed.

Rollback: switch both `current` symlinks back to `20261023-153023-admin` and restart `aicase-backend`. The additive migration remains compatible with that release; retain new tables, saved settings, media and backups rather than reversing migrations. The deployment script restores pointers automatically if activation checks fail.

## Order integration deployed (2026-10-24 22:45 Asia/Shanghai)

Active web and backend release: `20261024-224445-orders`. Previous release: `20261023-193732-catalog`. Database/media/config backup completed at `/var/backups/aicase/data-20261024T144553Z`.

- Migration 0003 adds browser order ownership hashes, unique checkout request keys, test-payment mode, revisions, station ID and ready status. No catalog, price, account or role values were overwritten. Existing Python environment, service and Nginx settings are unchanged.
- Storefront confirms orders through the server, records private design/photo snapshots, lists browser-owned orders at `/#orders`, and synchronizes revisions, cancellation and simulated printing/collection. Admin `/admin/orders` shows design preview, mode, status, details and editable support notes.
- Price is resolved on the server. During final online verification the active print price was USD 9.00 (the local preview database still uses USD 9.90). Existing order amounts are preserved.
- 141 web files and 25 backend files verified against SHA-256 manifests. Served index, simple-app.js, simple.css and order-service.js match local bytes. 108 storefront tests and 36 backend tests pass; admin production build, Django check and migration drift check pass.
- Local browser verified collection/photo checkout, design revision, QR replacement, print/ready/collected state, cancellation, server order history, admin preview and support-note persistence. The 390px viewport has no horizontal overflow. Screenshots and reports: `test-results/order-integration/`.
- Real HTTPS requests verified concurrent identical checkout requests return one order (201/200), foreign/missing ownership denial, price tamper rejection, old-code rejection, edit locking, station transitions, photo snapshot, cancellation, admin detail/notes and forbidden payment-state edits. Two clearly marked integration-test orders are retained with support notes; no actual charges or printing occurred. References are in `live-verification.json`. No recent backend service errors; service active.
- Public browser navigation timed out, so no public browser visual check is claimed. Same-build local UI verification plus public API/hash verification completed.

Rollback: switch both `current` pointers back to `20261023-193732-catalog` and restart `aicase-backend`. Keep additive migration 0003 and all order data. Older versions cannot manage the new server-order workflow; restore the new release to resume it. The deployment used an activation-failure trap to restore both pointers.

Current boundary: payment and station actions remain explicitly simulated. Customer access depends on a private browser key; no account recovery or cross-device station authentication yet. Private order photos are in the database snapshot, not public media. Existing browser-only orders are not silently imported.

## Image optimization deployed (2026-10-25 23:56 Asia/Shanghai)

Active web and backend release: `20261025-235321-images`; previous release `20261024-224445-orders` retained. Database/media/config backup: `/var/backups/aicase/data-20261025T155623Z`; previous Nginx config: `/var/backups/aicase/nginx-before-20261025-235321-images.conf`. No schema, catalog, price or order changes.

- 222 web files and 29 backend files passed SHA-256 verification. Static images have content-addressed WebP display derivatives and responsive selection; originals and saved design paths are retained. The largest display versions of 26 source images total 6.75 MB versus 68.20 MB originally (90.1% reduction). Small tiles request smaller files still.
- Admin uploads preserve normalized full-resolution originals and automatically create previews. Existing public uploads can use the idempotent `optimize_library_images` command; there were no existing uploads needing backfill on this server. Private order snapshots are not part of the public image pipeline.
- Noncritical images load lazily and decode asynchronously. In the local browser, all 9 images inside the collapsed AI section remained unloaded; expansion requested WebP previews. Desktop and 390-pixel mobile layout were checked with no horizontal overflow.
- Nginx caches only content-addressed static previews and public library previews for one year with immutable. Entry files and API responses retain existing cache policy. Nginx configuration and backend health passed.
- 111 frontend tests, 38 backend tests and admin production build passed; final image edge-case tests passed. HTTPS served six changed source files and sample derivatives with matching bytes and correct WebP/cache headers. A disposable 2600×1300 transparent upload preserved dimensions/alpha, returned 320/640/1280 previews, and served successfully. Its files were removed after verification; audit event retained.
- Production browser navigation timed out again; visual checks were performed locally, while production was checked through HTTPS and the real admin upload API. Evidence is in ignored `test-results/image-optimization/`.

Rollback: restore the above saved Nginx config, switch both current symlinks back to `20261024-224445-orders`, restart `aicase-backend`, validate and reload Nginx. Keep media originals/derivatives and all order data. See `docs/image-performance.md` for rebuilding and maintaining images.

## Photo replacement clears old artwork (2026-10-26 00:24 Asia/Shanghai)

Web release `20261026-002343-photo-reset` replaces `20261025-235321-images`. Backend remains on `20261025-235321-images`. Selecting a new uploaded photo or a new sample now clears the previous photo's stickers, text, retained template layers and placement only after the image has been decoded and saved. Merely switching source tabs retains existing behavior; applying an AI effect to the same photo still preserves its artwork. The upload area explains that choosing a photo starts with cleared graphics/text.

111 frontend tests passed. Local browser reproduced 9 stale layers before the fix, then verified 0 layers after replacement, persistence across reload, same-file reselection, clean checkout preview and new-sample selection. Invalid images retained the current artwork. All 222 web files passed SHA-256 checks; HTTPS served the new script hash and backend health remained OK. No payment was submitted during these checks. Evidence: ignored `test-results/photo-replacement/`.

Rollback requires only switching the web current pointer back to `20261025-235321-images`; no backend restart, schema change or Nginx change is involved.

## Collection selection clears previous edits (2026-10-26)

Web release `20261026-003635-collection-reset` replaces `20261026-002343-photo-reset`; backend remains `20261025-235321-images`. The reported leftover graphics came from per-template saved drafts, not stale image responses. Explicitly choosing a collection thumbnail (including the same template) or a gallery card now restores that template's original layers, text, positions and effect. The picker explains that choosing a design clears its previous edits. Refreshing or returning from checkout continues to preserve the current draft.

111 frontend tests passed. Local browser reproduced 6 stale layers after switching away and back, then verified only the original 3 remain after the fix. Same-template reselection, switching between templates, gallery selection, active inline-text replacement, draft retention on reload and clean checkout preview passed; no order/payment was submitted. All 222 web files passed SHA-256 verification, the public script matches local bytes with `Cache-Control: no-cache`, and backend health is OK. Evidence: ignored `test-results/collection-reset/`. Public browser inspection was unavailable; local UI checks and public HTTPS verification were used.

Rollback: switch only the web current pointer back to `20261026-002343-photo-reset`. No backend, Nginx, schema or order data changes.

## Keep editor drafts; start fresh from home (2026-10-26)

Web release `20261026-004635-draft-session` replaces `20261026-003635-collection-reset`, refining the previous selection behavior. Editor thumbnails retain each design's draft, including reselecting the current design. Only selecting a design card from the home/gallery starts a fresh collection editing session and clears all previous collection drafts, so switching templates cannot resurrect an earlier session. Ordinary reloads and returning from checkout preserve drafts. The on-page hint reflects this behavior.

111 frontend tests passed. Local browser checks verified separate graphics/text on two designs survive repeated switching, same-design selection and reload; selecting from home clears both drafts, and edits in the new session are again preserved. All 222 web files passed SHA-256 verification; the public script matches local bytes with `Cache-Control: no-cache` and backend health remains OK. Evidence: ignored `test-results/design-draft-session/`. Public browser visual verification was unavailable; the UI was checked locally. No payments or orders were created.

Backend remains `20261025-235321-images`; Nginx, schema and order data are unchanged. Rollback only requires switching the web current pointer back to `20261026-003635-collection-reset`.
