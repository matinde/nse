from django.contrib import admin
from django.http import HttpResponse
from django.urls import path

from market.views import chat_view, dashboard, login_view, logout_view


def health(request):
    return HttpResponse("ok")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health),
    path("login/", login_view, name="login"),
    path("logout/", logout_view, name="logout"),
    path("chat/", chat_view, name="chat"),
    path("", dashboard, name="dashboard"),
]
