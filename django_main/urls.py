from django.contrib import admin
from django.urls import path
from django_activitypub.views import (
    webfinger, profile, followers, inbox, outbox, community_inbox,
    NodeInfo, SiteInfo, FederatedInstances, Root,
    PostDetail, SetupServiceActor, SendNote, FollowUser,
    UnfollowUser, SetupPersonActor, FollowCommunity,
    CommunityDetail, SetupCommunityActor, SetupGroupActor,
    SendLemmyPost
)




urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),

    # Root and Node Information
    path('', Root.as_view(), name='root'),
    path("nodeinfo/2.0.json", NodeInfo.as_view(), name="nodeinfo"),
    path("api/v3/site", SiteInfo.as_view(), name="site_info"),
    path('api/v3/federated_instances', FederatedInstances.as_view(), name='federated-instances'),

    # WebFinger and ActivityPub profile paths
    path('.well-known/webfinger', webfinger, name='activitypub-webfinger'),
    path('pub/<slug:username>', profile, name='activitypub-profile'),
    path('pub/<slug:username>/followers', followers, name='activitypub-followers'),
    path('pub/<str:username>/inbox', inbox, name='activitypub-inbox'),
    path('pub/<slug:username>/outbox', outbox, name='activitypub-outbox'),

    # Post details
    path('pub/<str:username>/<int:pk>/', PostDetail.as_view(), name='post_detail'),

    # Community-specific paths for Lemmy compatibility using `/c/`
    path('c/<slug:community_name>', profile, name='community-profile'),
    path('c/<slug:community_name>/followers', followers, name='community-followers'),
    path('c/<slug:community_name>/inbox', community_inbox, name='community-inbox'),
    path('c/<slug:community_name>/outbox', outbox, name='community-outbox'),

    # Actor setup endpoints
    path('setup-service-actor/', SetupServiceActor.as_view(), name='setup_service_actor'),
    path('setup-person-actor/', SetupPersonActor.as_view(), name='setup_person_actor'),
    path('setup-community-actor/', SetupCommunityActor.as_view(), name='setup_community_actor'),
    path('setup-group-actor/', SetupGroupActor.as_view(), name='setup_group_actor'),

    # Follow and Unfollow actions
    path('follow-user/', FollowUser.as_view(), name='follow_user'),
    path('unfollow-user/', UnfollowUser.as_view(), name='unfollow_user'),
    path('follow-community/', FollowCommunity.as_view(), name='follow_community'),

    # Send post paths
    path('send-note/', SendNote.as_view(), name='send_note'),
    path('send-lemmy-post/', SendLemmyPost.as_view(), name='send_lemmy_post'),

    # Community detail view for JSON summary
    path('community-detail/<str:community_name>/', CommunityDetail.as_view(), name='community_detail_summary'),
]
























