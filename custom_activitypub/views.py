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
from django.urls import reverse
import requests

logger = logging.getLogger(__name__)

class NodeInfoView(View):
    def get(self, request, *args, **kwargs):
        # Define the metadata about your instance for the nodeinfo endpoint
        node_info = {
            "version": "2.0",
            "software": {
                "name": "YourSoftwareName",  # Customize this
                "version": "YourVersion"      # Customize this
            },
            "protocols": ["activitypub"],
            "services": {
                "inbound": [],
                "outbound": []
            },
            "openRegistrations": False,  # Adjust based on your instance's policy
            "usage": {
                "users": {
                    "total": 100  # Replace with actual user count if available
                }
            },
            "metadata": {}
        }
        return JsonResponse(node_info, content_type="application/json")
    
class SiteInfoView(View):
    def get(self, request, *args, **kwargs):
        # Provide general information about the site for the site info endpoint
        site_data = {
            "site_name": "Your Site Name",          # Customize as needed
            "description": "Your Site Description", # Customize as needed
            "version": "YourVersion",               # Customize version
            # Add any other relevant site data here
        }
        return JsonResponse(site_data, content_type="application/json")




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
class SetupGroupActorView(View):
    def post(self, request, *args, **kwargs):
        data = json.loads(request.body)
        group_name = data.get('group_name')
        group_description = data.get('group_description')

        # Extract URLs for icon and image
        group_icon_url = data.get('icon', {}).get('url')
        group_image_url = data.get('image', {}).get('url')

        group_langs = data.get('language', [{"identifier": "en", "name": "English"}])

        if not group_name or not group_description:
            return JsonResponse({"error": "group_name and group_description are required."}, status=400)

        preferred_username = group_name.lower().replace(" ", "_")

        # Create a unique user for this group
        unique_username = f"group_{preferred_username}_{uuid.uuid4().hex[:6]}"
        user = get_user_model().objects.create_user(username=unique_username, password='groupdefaultpass')

        # Create or retrieve the group actor
        group_actor, actor_created = LocalActor.objects.get_or_create(
            user=user,
            preferred_username=preferred_username,
            defaults={
                'actor_type': 'G',  # 'G' for Group
                'domain': 'ap.staythepath.lol',
                'name': group_name,
                'summary': group_description,
                'icon': group_icon_url,
                'image': group_image_url,
                'community_name': group_name,
                'community_description': group_description
            }
        )

        # Assign URLs for ActivityPub endpoints under the /c/ path
        group_actor.inbox = f"/c/{preferred_username}/inbox/"
        group_actor.outbox = f"/c/{preferred_username}/outbox/"

        # Set custom fields
        group_actor.language = group_langs
        group_actor.postingRestrictedToMods = False

        # Optional endpoints or settings
        shared_inbox_url = f"https://{group_actor.domain}/inbox"
        group_actor.endpoints = {'sharedInbox': shared_inbox_url}
        
        # Set public key info
        group_actor.publicKey = {
            "id": f"https://ap.staythepath.lol/c/{preferred_username}#main-key",
            "owner": f"https://ap.staythepath.lol/c/{preferred_username}",
            "publicKeyPem": group_actor.public_key
        }

        # Save group actor with updated attributes
        group_actor.save()

        # Send response with all attributes using /c/ URLs
        return JsonResponse({
            "id": f"https://ap.staythepath.lol/c/{preferred_username}/",
            "type": "Group",
            "preferredUsername": group_actor.preferred_username,
            "name": group_actor.name,
            "summary": group_actor.summary,
            "source": {
                "content": group_actor.community_description,
                "mediaType": "text/markdown"
            },
            "sensitive": False,
            "icon": {
                "type": "Image",
                "url": group_icon_url
            },
            "image": {
                "type": "Image",
                "url": group_image_url
            },
            "inbox": f"https://ap.staythepath.lol/c/{preferred_username}/inbox/",
            "followers": f"https://ap.staythepath.lol/c/{preferred_username}/followers/",
            "attributedTo": f"https://ap.staythepath.lol/c/{preferred_username}/moderators",
            "featured": f"https://ap.staythepath.lol/c/{preferred_username}/featured",
            "postingRestrictedToMods": group_actor.postingRestrictedToMods,
            "endpoints": {
                "sharedInbox": shared_inbox_url
            },
            "outbox": f"https://ap.staythepath.lol/c/{preferred_username}/outbox/",
            "publicKey": group_actor.publicKey,
            "language": group_langs,
            "published": group_actor.created_at.isoformat(),
            "updated": group_actor.updated_at.isoformat()
        }, content_type="application/activity+json")




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
class SetupCommunityActorView(View):
    def post(self, request, *args, **kwargs):
        data = json.loads(request.body)
        community_name = data.get('community_name')
        community_description = data.get('community_description')

        if not community_name or not community_description:
            return JsonResponse({"error": "community_name and community_description are required."}, status=400)

        # Generate a unique username for each community
        unique_username = f"community_{community_name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
        
        # Create a unique user for this community
        user = get_user_model().objects.create_user(username=unique_username, password='adminpassword')

        preferred_username = community_name.lower().replace(" ", "_")

        # Now create the LocalActor for this new user
        community_actor = LocalActor.objects.create(
            user=user,
            preferred_username=preferred_username,
            actor_type='C',  # 'C' for Community
            domain='ap.staythepath.lol',
            name=community_name,
            summary=community_description
        )

        # Dynamically link to the actor's inbox and outbox routes
        community_actor.inbox = reverse('activitypub-inbox', kwargs={'username': preferred_username})
        community_actor.outbox = reverse('activitypub-outbox', kwargs={'username': preferred_username})
        community_actor.save()

        return JsonResponse({
            'message': f"Community actor '{community_name}' created.",
            'actor_url': community_actor.account_url
        })



        
# @method_decorator(csrf_exempt, name='dispatch')
# class AnnounceCommunityActorView(View):
#     def post(self, request, *args, **kwargs):
#         data = json.loads(request.body)
#         actor_username = data.get('actor_username')  # username of the community actor
#         target_url = data.get('target_url')  # Target server inbox URL for the announcement

#         if not actor_username or not target_url:
#             return JsonResponse({
#                 "error": "Both 'actor_username' and 'target_url' are required."
#             }, status=400)

#         try:
#             # Retrieve the community actor
#             community_actor = LocalActor.objects.get(preferred_username=actor_username, actor_type='C')
#             logger.debug(f"Announcing community actor {actor_username} to {target_url}")
#         except LocalActor.DoesNotExist:
#             return JsonResponse({
#                 "error": f"Community actor with username '{actor_username}' not found."
#             }, status=404)

#         # Construct the Announce activity
#         announce_activity = {
#             "@context": "https://www.w3.org/ns/activitystreams",
#             "id": f"https://ap.staythepath.lol/{uuid.uuid4()}",
#             "type": "Announce",
#             "actor": community_actor.account_url,
#             "object": community_actor.account_url  # Announcing the community actor's own URL
#         }

#         # Send the Announce activity to the specified target inbox
#         response = signed_post(
#             url=target_url,
#             private_key=community_actor.private_key.encode('utf-8'),
#             public_key_url=f"{community_actor.account_url}#main-key",
#             body=json.dumps(announce_activity)
#         )

#         # Check the response status and log accordingly
#         if response.status_code in (200, 201, 202):
#             logger.info(f"Successfully announced {actor_username} to {target_url}")
#             return JsonResponse({
#                 'message': f"Community actor '{actor_username}' announced to {target_url}.",
#                 'actor_url': community_actor.account_url
#             })
#         else:
#             logger.error(f"Failed to announce: {response.status_code} {response.text}")
#             return JsonResponse({
#                 'message': f"Community actor '{actor_username}' failed to announce to {target_url}.",
#                 'actor_url': community_actor.account_url,
#                 'error': response.text
#             }, status=response.status_code)

class RootView(View):
    def get(self, request, *args, **kwargs):
        data = {
            "name": "StayThePath ActivityPub Server",
            "description": "This server aggregates posts from the Fediverse.",
            "urls": {
                "nodeinfo": "/nodeinfo/2.0.json",
                "webfinger": "/.well-known/webfinger",
                "public_inbox": "/pub/community2/inbox/"  # Update with relevant public inbox if needed
            }
        }
        return JsonResponse(data)
    
class FederatedInstancesView(View):
    def get(self, request, *args, **kwargs):
        # Aggregate RemoteActor domains to identify instances
        linked_domains = RemoteActor.objects.filter(profile__linked=True).values_list('domain', flat=True).distinct()
        allowed_domains = RemoteActor.objects.filter(profile__allowed=True).values_list('domain', flat=True).distinct()
        blocked_domains = RemoteActor.objects.filter(profile__blocked=True).values_list('domain', flat=True).distinct()

        data = {
            "federated_instances": {
                "linked": list(linked_domains),
                "allowed": list(allowed_domains),
                "blocked": list(blocked_domains)
            }
        }
        return JsonResponse(data, content_type="application/json")

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
class SendLemmyPostView(View):
    def post(self, request, *args, **kwargs):
        # Extract data from the request
        data = json.loads(request.body)
        username = data.get('username')
        message = data.get('message', 'This is a test post content.')
        title = data.get('title', 'Default Post Title')
        community_name = data.get('community_name')
        logger.debug(f"Using community name: {community_name}")

        # Retrieve the user and base URI
        try:
            user = get_user_model().objects.get(username=username)
            local_actor = LocalActor.objects.get(user=user)  # Get LocalActor instance
        except (get_user_model().DoesNotExist, LocalActor.DoesNotExist):
            logger.error(f"User or LocalActor not found for username: {username}")
            return JsonResponse({"error": "User or LocalActor not found"}, status=404)
        
        base_uri = 'https://ap.staythepath.lol'

        # Construct community URLs dynamically using base_uri
        community_inbox = f"{base_uri}/c/{community_name}/inbox"
        community_actor = f"{base_uri}/c/{community_name}"

        # Create a new post, setting the LocalActor instance in attributed_to
        post = YourModel.objects.create(
            author=user,
            content=message
        )

        # Prepare "Create" activity to be sent to the Lemmy community inbox
        create_activity = {
            "@context": ["https://www.w3.org/ns/activitystreams", "https://w3id.org/security/v1"],
            "type": "Create",
            "actor": local_actor.account_url,  # Use the actor's account URL directly
            "to": [community_actor, "https://www.w3.org/ns/activitystreams#Public"],
            "cc": [f"{community_actor}/followers"],
            "object": {
                "type": "Page",
                "id": f"{base_uri}/post/{post.id}",
                "attributedTo": local_actor.account_url,  # Corrected to use LocalActor's URL
                "to": [community_actor, "https://www.w3.org/ns/activitystreams#Public"],
                "audience": community_actor,
                "name": title,
                "content": f"<p>{message}</p>",
                "mediaType": "text/html",
                "source": {
                    "content": message,
                    "mediaType": "text/markdown"
                },
                "sensitive": False,
                "commentsEnabled": True,
                "published": post.created_at.isoformat(),
                "updated": post.updated_at.isoformat() if post.updated_at else None
            }
        }

        # Send "Create" activity to the dynamically defined Lemmy community inbox
        self.send_to_community_inbox(create_activity, community_inbox=community_inbox)

        return JsonResponse({
            'message': "Post successfully created and sent to Lemmy community.",
            'content_url': create_activity["object"]["id"]
        })

    def send_to_community_inbox(self, activity_data, community_inbox):
        """
        Helper function to post data to the community inbox.
        """
        headers = {"Content-Type": "application/activity+json"}
        try:
            response = requests.post(community_inbox, json=activity_data, headers=headers)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Failed to send activity to Lemmy community inbox: {e}")


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
        
@method_decorator(csrf_exempt, name='dispatch')
class CommunityDetailView(View):
    def get(self, request, community_name, *args, **kwargs):
        # Fetch the community actor using the community name
        community_actor = get_object_or_404(LocalActor, community_name=community_name)

        data = {
            "id": community_actor.account_url,
            "name": community_actor.name,
            "description": community_actor.community_description,
        }
        return JsonResponse(data)

