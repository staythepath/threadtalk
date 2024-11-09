from django.urls import path
from django_activitypub.views import webfinger, profile, followers, inbox, outbox, community_inbox

urlpatterns = [
    path('.well-known/webfinger', webfinger, name='activitypub-webfinger'),
    path('pub/<slug:username>', profile, name='activitypub-profile'),
    path('pub/<slug:username>/followers', followers, name='activitypub-followers'),
    path('pub/<slug:username>/inbox', inbox, name='activitypub-inbox'),
    path('pub/<slug:username>/outbox', outbox, name='activitypub-outbox'),

    # Community endpoints with /c/ for Lemmy compatibility
    path('c/<slug:community_name>', profile, name='community-profile'),
    path('c/<slug:community_name>/followers', followers, name='community-followers'),
    path('c/<slug:community_name>/inbox', community_inbox, name='community-inbox'),
    path('c/<slug:community_name>/outbox', outbox, name='community-outbox'),
]
