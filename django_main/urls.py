"""
URL configuration for django_main project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from custom_activitypub.views import YourModelDetailView  # Adjust this import based on your structure
from django_activitypub.views import webfinger, profile, followers, inbox, outbox

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", include("django_activitypub.urls")),  # Include activitypub URLs
    path('pub/testuser/<int:pk>/', YourModelDetailView.as_view(), name='yourmodel_detail'),
    path('pub/<str:username>/', profile, name='activitypub-profile'),
    path('pub/<str:username>/followers/', followers, name='activitypub-followers'),
    path('pub/<str:username>/inbox/', inbox, name='activitypub-inbox'),
    path('pub/<str:username>/outbox/', outbox, name='activitypub-outbox'),
    path('.well-known/webfinger', webfinger, name='webfinger'),
]
