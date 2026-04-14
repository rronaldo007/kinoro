from django.urls import path

from . import views

urlpatterns = [
    path("vp/login/", views.login, name="vp-login"),
    path("vp/logout/", views.logout, name="vp-logout"),
    path("vp/account/", views.account, name="vp-account"),
    path("vp/projects/", views.project_list, name="vp-projects"),
    path(
        "vp/projects/<str:project_id>/",
        views.project_detail,
        name="vp-project-detail",
    ),
]
