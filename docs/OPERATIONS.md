# Operations — running Kinoro + Video Planner together

Pragmatic runbook for the dev environment. How the two stacks interact,
where state lives, what to do when something jams.

Production packaging (AppImage / DMG / NSIS) is M8. Everything here is
about the **dev** path: Video Planner via Docker Compose + Kinoro via
Vite + Electron + a local Django sidecar.

---

## Topology

```
              ┌────────────────────────────────────────┐
              │  video-planner3 / scripts/start.sh     │
              │                                        │
              │  • docker compose up (VP)              │
              │  • migrate + seed test users           │
              │  • install kinoro:// .desktop handler  │
              │  • wait for Vite on :5174              │
              │  • npm run start:dev (Electron)        │
              └────────────────────────────────────────┘
                              │
             ┌────────────────┼─────────────────────────┐
             │                │                         │
             ▼                ▼                         ▼
   ┌───────────────┐   ┌──────────────┐       ┌─────────────────┐
   │ VP frontend   │   │ Kinoro UI    │       │ VP backend      │
   │ :5173 (Vite)  │   │ :5174 (Vite) │       │ :8000 (Django   │
   │ Docker        │   │ host process │       │  in Docker)     │
   └───────────────┘   └──────────────┘       └─────────────────┘
                              │
                              ▼
                       ┌─────────────────────┐
                       │ Electron main       │
                       │   (host process)    │
                       │   spawns → python   │
                       │                     │
                       │   Django sidecar    │
                       │   127.0.0.1:<rand>  │
                       │   KINORO_DATA_DIR=  │
                       │     ~/.config/...   │
                       └─────────────────────┘
```

### What `scripts/start.sh` does, in order

1. Brings up VP's Docker Compose stack (MariaDB, Redis, backend,
   Celery, Vite on :5173).
2. Runs VP migrations + seeds (test users, example projects, public-URL
   seed videos for import tests).
3. Installs the `kinoro://` URL handler as a user-scoped `.desktop`
   entry (`~/.local/share/applications/kinoro-dev.desktop`) so the
   protocol link from VP opens Kinoro.
4. Ensures the Kinoro Python venv exists at `kinoro/server/.venv/` and
   migrates the sidecar's SQLite at `~/.config/kinoro-app/data/`.
5. Launches the Kinoro Vite dev server on `:5174` (hard-coded; see
   `strictPort` note below).
6. Waits up to 10 s for Vite to bind, then launches Electron via
   `npm run start:dev`.

`refresh.sh` is the same minus the first-time setup steps. `stop.sh`
pkills Kinoro processes and brings the VP stack down.

---

## Canonical paths

| Thing | Path | Notes |
|---|---|---|
| Sidecar SQLite | `~/.config/kinoro-app/data/kinoro.sqlite3` | One path only — never a repo-local fallback. |
| Ingested media / imports | `~/.config/kinoro-app/data/vp-imports/` | Files copied in from VP imports (live API + ZIP). |
| ZIP uploads staged | `~/.config/kinoro-app/data/vp-zip-imports/` | Where `POST /api/import/vp/zip/` writes the uploaded ZIP before the thread consumes it. |
| Proxy MP4s | `~/.config/kinoro-app/data/proxies/` | 720p H.264 + AAC, built by `engine.ffmpeg.build_proxy`. |
| Renders (M5+) | `~/.config/kinoro-app/data/renders/` | Final MP4s from `timeline_render`. |
| Sidecar log | `~/.config/kinoro-app/data/kinoro.log` | Rotating, DEBUG level. 5 MB × 3 backups. |
| Electron / Vite logs (dev) | `video-planner3/.cache/kinoro-{ui,app}.log` | Only populated when started via `scripts/start.sh`. |
| VP docker logs | `docker compose logs -f backend` | Standard compose commands. |

`KINORO_DATA_DIR` is the one env var that controls all of the above. If
you override it (for tests, for a second instance, etc.) make sure
migrations run against the same value the sidecar will later read —
otherwise you get the classic "my migrations succeeded but the app has
no tables" trap.

---

## The `--no-sandbox` flag

Electron on Linux wants `CAP_SYS_ADMIN` to set up its SUID sandbox. On
most developer machines — especially anything installed via a distro
package manager or `node_modules` — the SUID helper isn't root-owned
with setuid, so Electron refuses to start:

```
FATAL:setuid_sandbox_host.cc: The SUID sandbox helper binary was found,
but is not configured correctly.
```

The workaround is to pass `--no-sandbox` at Electron startup. This
**weakens the renderer sandbox** and we don't want it in packaged
builds. So:

| npm script | Passes `--no-sandbox`? | When to use |
|---|---|---|
| `npm start` | No | Production default; what `dist:*` ultimately mimics. |
| `npm run start:dev` | Yes | Linux dev when the SUID helper isn't set up. |

`video-planner3/scripts/start.sh` and `refresh.sh` use `start:dev`.
Packaging (`npm run dist:*`) uses the production flag set.

If you want a properly-sandboxed dev run, fix the SUID helper:

```bash
sudo chown root:root kinoro/app/node_modules/electron/dist/chrome-sandbox
sudo chmod 4755       kinoro/app/node_modules/electron/dist/chrome-sandbox
```

Then run `npm start`. You'll have to redo this whenever `npm install`
unpacks a new Electron version.

---

## Known issues

### Vite `strictPort: true` on 5174

`kinoro/ui/vite.config.ts` hard-binds to `:5174`. Electron's main
process hard-codes `http://localhost:5174` as its renderer URL. If the
port is already taken, Vite bails out and Electron opens a blank
window. `scripts/start.sh` waits for the port; if it doesn't come up
after 10 s the script logs the Vite stderr path and skips the Electron
launch instead of hanging forever.

Fix: find what's on 5174 (`ss -tlnp | grep 5174`), kill it, rerun.

### Google CDN seed URLs retired

The original `seed_video_resources` management command pointed at
`commondatastorage.googleapis.com/gtv-videos-bucket/...` for importable
test clips. Those URLs now 403 from server-side fetches. The current
seed uses MDN / w3schools / samplelib sample clips. If you add new
seeds, please use one of those hosts or add a similarly-liberal
referer-free one.

### Background-thread SQLite locks in tests

`ingest_async` starts a daemon thread that writes to SQLite. The
pytest-django `db` fixture rolls back inside the test, which the thread
doesn't know about, so you can occasionally see `OperationalError:
database table is locked` or `Save with update_fields did not affect
any rows` **warnings** (not failures) when tests exit.

Integration tests that don't exercise the ingest pipeline itself should
stub `ingest_async` to a no-op (see
`apps/import_vp/tests/test_zip_import.py`). Real ingest integration
lives in `apps/media/tests/test_ingest_integration.py` where the
pipeline is the thing under test.

---

## Running tests

The sidecar tests live under `server/apps/*/tests/`. They use
pytest-django and require an isolated `KINORO_DATA_DIR` so they don't
stomp on the live sidecar's SQLite:

```bash
cd kinoro/server
KINORO_DATA_DIR=/tmp/kinoro-test .venv/bin/python -m pytest -q
```

The `conftest.py` also sets `KINORO_DATA_DIR` to a per-session tmp dir
if one isn't exported, but it has to run before `django.setup()` — so
exporting one yourself is safer than relying on timing.

The `tiny_video` fixture shells out to `ffmpeg` to generate a 1-second
test clip; tests using it auto-skip if ffmpeg isn't on `$PATH`.

Current counts: **80 tests** across `apps.core`, `apps.media`,
`apps.import_vp`.

---

## Clean shutdown

`scripts/stop.sh` runs these `pkill` patterns — keep them handy for
ad-hoc cleanup:

```bash
pkill -f "kinoro/ui/node_modules/.*vite"
pkill -f "kinoro/app/node_modules/.*electron"
pkill -f "kinoro/server/.venv/bin/python"
# Plus: docker compose down for VP, and free any ports 5173/5174/8000/3306/6379.
```

The patterns match the cmdline prefix, so running two copies of Kinoro
from two separate checkouts is safe — each pkill scopes to its own
checkout path.

---

## Resetting a stuck state

- **Stuck VPAccount** (session expired, wrong base URL, whatever): delete
  via the sidecar shell:
  ```bash
  cd kinoro/server
  KINORO_DATA_DIR=~/.config/kinoro-app/data .venv/bin/python manage.py shell \
      -c "from apps.import_vp.models import VPAccount; VPAccount.objects.all().delete()"
  ```
  Or hit `POST /api/import/vp/logout/`.

- **Clear all media**: `rm -rf ~/.config/kinoro-app/data/{media,proxies,vp-imports,vp-zip-imports}`
  then `DELETE` rows via the Django admin (there's no bulk-clear
  endpoint yet; admin is at the sidecar's `/admin/`).

- **Reset sidecar DB** (nuclear): `rm ~/.config/kinoro-app/data/kinoro.sqlite3`
  and rerun migrations. You lose all local projects and import history.
