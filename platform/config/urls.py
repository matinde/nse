from django.contrib import admin
from django.http import HttpResponse
from django.urls import path


def health(request):
    return HttpResponse("ok")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health),
]
