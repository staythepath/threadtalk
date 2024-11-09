from django.contrib import admin
from django.urls import path, include
from custom_activitypub.views import (
    PostDetailView, SetupServiceActorView, SendPostView, FollowUserView, 
    UnfollowUserView, SetupPersonActorView, FollowCommunityView, 
    CommunityDetailView, SetupCommunityActorView, SetupGroupActorView, 
    NodeInfoView, SiteInfoView, FederatedInstancesView, RootView, SendLemmyPostView
)
from django_activitypub.views import webfinger, profile, followers, inbox, outbox, community_profile, community_inbox

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", include("django_activitypub.urls")),  # Include ActivityPub URLs
    path('pub/<str:username>/<int:pk>/', PostDetailView.as_view(), name='yourmodel_detail'),
    path('pub/<str:username>/', profile, name='activitypub-profile'),
    path('pub/<str:username>/followers/', followers, name='activitypub-followers'),
    path('pub/<str:username>/inbox/', inbox, name='activitypub-inbox'),
    path('pub/<str:username>/outbox/', outbox, name='activitypub-outbox'),
    path('.well-known/webfinger', webfinger, name='webfinger'),

    # Community-specific URLs using /c/ convention
    path('c/<str:community_name>/', community_profile, name='community_detail'),
    path('c/<str:community_name>/followers/', followers, name='community-followers'),
    path('c/<str:community_name>/inbox/', inbox, name='community-inbox'),


    path('c/<str:community_name>/outbox/', outbox, name='community-outbox'),

    # Other setup paths
    path('setup-service-actor/', SetupServiceActorView.as_view(), name='setup_service_actor'),
    path('setup-person-actor/', SetupPersonActorView.as_view(), name='setup_person_actor'),
    path('setup-community-actor/', SetupCommunityActorView.as_view(), name='setup_community_actor'),
    path('setup-group-actor/', SetupGroupActorView.as_view(), name='setup_group_actor'),
    path("nodeinfo/2.0.json", NodeInfoView.as_view(), name="nodeinfo"),
    path("api/v3/site", SiteInfoView.as_view(), name="site_info"),
    path('api/v3/federated_instances', FederatedInstancesView.as_view(), name='federated-instances'),
    path('', RootView.as_view(), name='root_view'),
    
    # Send post to Mastodon
    path('send-post/', SendPostView.as_view(), name='send_post'),
    
    # New endpoint for sending posts to Lemmy
    path('send-lemmy-post/', SendLemmyPostView.as_view(), name='send_lemmy_post'),
]
