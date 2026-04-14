"""Video Planner import — REST endpoints wired in M1.

Planned routes (already announced in urls.py as placeholders):

    POST /api/import/vp/login/               body: {base_url, email, password}
    POST /api/import/vp/logout/              clears stored VPAccount
    GET  /api/import/vp/projects/            list remote projects (proxies to VP)
    POST /api/import/vp/projects/<id>/       start a live-API import
    POST /api/import/vp/zip/                 multipart upload → start a ZIP import
    GET  /api/import/vp/jobs/<id>/           import status + progress
    GET  /api/import/vp/account/             current stored account (or 404)

The actual viewsets land in M1 together with the import pipeline. For M0 the
app just registers itself so migrations run cleanly.
"""
