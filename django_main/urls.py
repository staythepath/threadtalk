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
from custom_activitypub.views import PostDetailView, SetupServiceActorView, SendPostView, FollowUserView, UnfollowUserView, SetupPersonActorView, FollowCommunityView, CommunityDetailView
from django_activitypub.views import webfinger, profile, followers, inbox, outbox

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", include("django_activitypub.urls")),  # Include activitypub URLs
    path('pub/<str:username>/<int:pk>/', PostDetailView.as_view(), name='yourmodel_detail'),
    path('pub/<str:username>/', profile, name='activitypub-profile'),
    path('pub/<str:username>/followers/', followers, name='activitypub-followers'),
    path('pub/<str:username>/inbox/', inbox, name='activitypub-inbox'),
    path('pub/<str:username>/outbox/', outbox, name='activitypub-outbox'),
    path('.well-known/webfinger', webfinger, name='webfinger'),
    path('setup-service-actor/', SetupServiceActorView.as_view(), name='setup_service_actor'),
    path('setup-person-actor/', SetupPersonActorView.as_view(), name='setup_person_actor'),
    path('send-post/', SendPostView.as_view(), name='send_post'),
    path('follow-user/', FollowUserView.as_view(), name='follow_user'),
    path('unfollow-user/', UnfollowUserView.as_view(), name='unfollow_user'),
    path('follow-community/', FollowCommunityView.as_view(), name='follow_community'),
    path('c/<str:community_name>/', CommunityDetailView.as_view(), name='community_detail'),

]
