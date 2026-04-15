from django.urls import path

from . import views

urlpatterns = [
    path("vp/adopt/", views.adopt, name="vp-adopt"),
    path("vp/login/", views.login, name="vp-login"),
    path("vp/logout/", views.logout, name="vp-logout"),
    path("vp/account/", views.account, name="vp-account"),
    path("vp/projects/", views.project_list, name="vp-projects"),
    path(
        "vp/projects/<str:project_id>/",
        views.project_detail,
        name="vp-project-detail",
    ),
    path(
        "vp/projects/<str:project_id>/import/",
        views.project_import,
        name="vp-project-import",
    ),
    path(
        "vp/zip/",
        views.project_import_zip,
        name="vp-project-import-zip",
    ),
    path(
        "vp/jobs/<uuid:job_id>/",
        views.import_job_detail,
        name="vp-import-job-detail",
    ),
]
