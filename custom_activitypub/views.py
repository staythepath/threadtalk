from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth import get_user_model  # Import for user model
from django_activitypub.models import LocalActor, Note, RemoteActor, Follower  # Required models from django_activitypub
from django_activitypub.signed_requests import signed_post  # Required for signed requests
from django_activitypub.webfinger import finger  # Required for WebFinger lookup
from django.shortcuts import render, get_object_or_404
from django_activitypub.models import LocalActor
import json
import uuid  # Required for generating unique IDs in Follow/Unfollow activities
from .models import YourModel
import logging  # For logging any issues if needed



class PostDetailView(View):
    def get(self, request, username, pk, *args, **kwargs):
        
        try:
            post = YourModel.objects.get(author__username=username, pk=pk)
            data = {
                "@context": "https://www.w3.org/ns/activitystreams",
                "type": "Note",
                "id": f"https://ap.staythepath.lol/pub/{username}/{pk}/",
                "content": post.formatted_content(),
                "published": post.created_at.isoformat(),
                "attributedTo": f"https://ap.staythepath.lol/pub/{username}/",
            }
            return JsonResponse(data, content_type="application/activity+json")
        except YourModel.DoesNotExist:
            return JsonResponse({"error": "Not Found"}, status=404)

@method_decorator(csrf_exempt, name='dispatch')
class SetupServiceActorView(View):
    def post(self, request, *args, **kwargs):
        data = json.loads(request.body)
        username = data.get('username', 'tester')  # Default to 'tester' if no username is provided
        password = data.get('password', 'testpassword')
        
        user, created = get_user_model().objects.get_or_create(
            username=username,
            defaults={'password': password}
        )
        actor, actor_created = LocalActor.objects.get_or_create(
            user=user,
            defaults={
                'preferred_username': username,
                'domain': 'ap.staythepath.lol',
                'name': username,
                'actor_type': 'S'
            }
        )
        base_uri = 'https://ap.staythepath.lol'
        data = {
            'user_created': created,
            'actor_created': actor_created,
            'base_uri': base_uri
        }
        return JsonResponse(data)
    
@method_decorator(csrf_exempt, name='dispatch')
class SetupPersonActorView(View):
    def post(self, request, *args, **kwargs):
        data = json.loads(request.body)
        username = data.get('username', 'tester')  # Default to 'tester' if no username is provided
        password = data.get('password', 'testpassword')
        
        user, created = get_user_model().objects.get_or_create(
            username=username,
            defaults={'password': password}
        )
        actor, actor_created = LocalActor.objects.get_or_create(
            user=user,
            defaults={
                'preferred_username': username,
                'domain': 'ap.staythepath.lol',
                'name': username,
                'actor_type': 'P'
            }
        )
        base_uri = 'https://ap.staythepath.lol'
        data = {
            'user_created': created,
            'actor_created': actor_created,
            'base_uri': base_uri
        }
        return JsonResponse(data)


@method_decorator(csrf_exempt, name='dispatch')
class SendPostView(View):
    def post(self, request, *args, **kwargs):
        data = json.loads(request.body)
        username = data.get('username', 'tester')
        message = data.get('message', 'This is a test post content.')

        user = get_user_model().objects.get(username=username)
        base_uri = 'https://ap.staythepath.lol'
        post = YourModel.objects.create(
            author=user,
            content=message
        )
        post.publish(base_uri=base_uri)
        
        note = Note.objects.filter(
            local_actor=LocalActor.objects.get(user=user),
            content__contains=message
        ).first()
        
        if note:
            data = {'message': "Note was successfully created and published.", 'content_url': note.content_url}
        else:
            data = {'error': "Failed to create or publish the note."}
        
        return JsonResponse(data)

@method_decorator(csrf_exempt, name='dispatch')
class FollowUserView(View):
    def post(self, request, *args, **kwargs):
        data = json.loads(request.body)
        local_actor_username = data.get('local_actor_username')
        remote_actor_handle = data.get('remote_actor_handle')
        
        if not local_actor_username or not remote_actor_handle:
            return JsonResponse({"error": "Both local_actor_username and remote_actor_handle are required."}, status=400)

        try:
            username, domain = remote_actor_handle.lstrip('@').split('@')
            webfinger_data = finger(username, domain)
            profile_data = webfinger_data.get("profile")
            remote_actor_url = profile_data.get("id")
            inbox_url = profile_data.get("inbox")
        except Exception as e:
            return JsonResponse({"error": "WebFinger lookup failed.", "details": str(e)}, status=400)
        
        local_actor = LocalActor.objects.get(preferred_username=local_actor_username)
        follow_activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "id": f"https://{local_actor.domain}/{uuid.uuid4()}",
            "type": "Follow",
            "actor": local_actor.account_url,
            "object": remote_actor_url
        }
        
        response = signed_post(
            url=inbox_url,
            private_key=local_actor.private_key.encode('utf-8'),
            public_key_url=f"{local_actor.account_url}#main-key",
            body=json.dumps(follow_activity)
        )
        
        if response.status_code == 202:
            return JsonResponse({"message": f"Successfully followed {remote_actor_handle}"})
        else:
            return JsonResponse({"error": f"Failed to follow: {response.status_code} {response.text}"})

@method_decorator(csrf_exempt, name='dispatch')
class UnfollowUserView(View):
    def post(self, request, *args, **kwargs):
        data = json.loads(request.body)
        local_actor_username = data.get('local_actor_username')
        remote_actor_url = data.get('remote_actor_url')
        
        if not local_actor_username or not remote_actor_url:
            return JsonResponse({"error": "Both local_actor_username and remote_actor_url are required."}, status=400)

        remote_actor = RemoteActor.objects.get(url=remote_actor_url)
        local_actor = LocalActor.objects.get(preferred_username=local_actor_username)
        
        undo_follow_activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "id": f"https://{local_actor.domain}/{uuid.uuid4()}",
            "type": "Undo",
            "actor": local_actor.account_url,
            "object": {
                "type": "Follow",
                "id": f"https://{local_actor.domain}/{uuid.uuid4()}",
                "actor": local_actor.account_url,
                "object": remote_actor.url
            }
        }
        
        inbox_url = remote_actor.profile.get('inbox', remote_actor.url + '/inbox')
        response = signed_post(
            url=inbox_url,
            private_key=local_actor.private_key.encode('utf-8'),
            public_key_url=f"{local_actor.account_url}#main-key",
            body=json.dumps(undo_follow_activity)
        )
        
        if response.status_code == 202:
            return JsonResponse({"message": f"Successfully unfollowed {remote_actor.handle}"})
        else:
            return JsonResponse({"error": f"Failed to unfollow: {response.status_code} {response.text}"})

@method_decorator(csrf_exempt, name='dispatch')
class FollowCommunityView(View):
    def post(self, request, *args, **kwargs):
        data = json.loads(request.body)
        local_actor_username = data.get('local_actor_username')
        community_url = data.get('community_url')
        
        if not local_actor_username or not community_url:
            return JsonResponse({"error": "Both local_actor_username and community_url are required."}, status=400)
        
        try:
            # Parse community WebFinger data (assuming Lemmy supports this)
            username, domain = community_url.split('@')[1].split('/')[-1], community_url.split('@')[-1]
            webfinger_data = finger(username, domain)
            profile_data = webfinger_data.get("profile")
            community_actor_url = profile_data.get("id")
            inbox_url = profile_data.get("inbox")
        except Exception as e:
            return JsonResponse({"error": "Failed to retrieve community WebFinger data.", "details": str(e)}, status=400)
        
        # Retrieve the local actor who is following the community
        local_actor = LocalActor.objects.get(preferred_username=local_actor_username)
        
        follow_activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "id": f"https://{local_actor.domain}/{uuid.uuid4()}",
            "type": "Follow",
            "actor": local_actor.account_url,
            "object": community_actor_url
        }
        
        # Send signed follow request
        response = signed_post(
            url=inbox_url,
            private_key=local_actor.private_key.encode('utf-8'),
            public_key_url=f"{local_actor.account_url}#main-key",
            body=json.dumps(follow_activity)
        )
        
        if response.status_code == 202:
            return JsonResponse({"message": f"Successfully followed community {community_url}"})
        else:
            return JsonResponse({"error": f"Failed to follow community: {response.status_code} {response.text}"})
        
from django.http import JsonResponse
from django.views import View
from django.shortcuts import get_object_or_404
from django_activitypub.models import LocalActor

class CommunityDetailView(View):
    def get(self, request, community_name, *args, **kwargs):
        # Fetch the community actor using the community name
        community_actor = get_object_or_404(LocalActor, community_name=community_name)

        # Construct the full JSON response with all required fields
        data = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "id": community_actor.account_url,  # Full URL for this community actor
            "type": "Group",
            "name": community_actor.name,
            "summary": community_actor.community_description,
            "preferredUsername": community_actor.preferred_username,
            "inbox": community_actor.inbox,  # Inbox URL for receiving activities
            "outbox": community_actor.outbox,  # Outbox URL for sending activities
            "followers": f"{community_actor.account_url}/followers",  # Followers URL
            "publicKey": {
                "id": f"{community_actor.account_url}#main-key",
                "owner": community_actor.account_url,
                "publicKeyPem": community_actor.public_key  # Actor's public key
            }
        }
        return JsonResponse(data, content_type="application/activity+json")


