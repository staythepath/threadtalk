import json
import re
import uuid
import urllib.parse
import logging  # For logging any issues if needed
import requests  # For handling HTTP requests to external services

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, resolve
from django.core.paginator import Paginator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth import get_user_model

from django_activitypub.models import ActorChoices, LocalActor, RemoteActor, Follower, Note
from django_activitypub.signed_requests import signed_post, SignatureChecker
from django_activitypub.webfinger import fetch_remote_profile, WebfingerException, finger

# Import YourModel if it's still needed in your views



# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)



def webfinger(request):
    resource = request.GET.get('resource')
    logger.debug("Received WebFinger request for resource: %s", resource)

    # Match resource formats and extract username/domain
    acct_m = re.match(r'^acct:(?P<username>.+?)@(?P<domain>.+)$', resource)
    if acct_m:
        username = acct_m.group('username')
        domain = acct_m.group('domain')
        logger.debug("Parsed account: username=%s, domain=%s", username, domain)
    elif resource.startswith('http'):
        parsed = urllib.parse.urlparse(resource)
        logger.debug("Parsed URL: %s", parsed)
        
        if parsed.scheme != request.scheme or parsed.netloc != request.get_host():
            logger.warning("Invalid resource scheme or host")
            return JsonResponse({'error': 'invalid resource'}, status=404)
        
        url = resolve(parsed.path)
        logger.debug("Resolved URL: %s", url)
        
        if url.url_name != 'activitypub-profile':
            logger.warning("Unknown resource type")
            return JsonResponse({'error': 'unknown resource'}, status=404)
        
        username = url.kwargs.get('username')
        domain = request.get_host()
    else:
        logger.error("Unsupported resource format")
        return JsonResponse({'error': 'unsupported resource'}, status=404)

    # Retrieve the actor based on parsed username and domain
    try:
        actor = LocalActor.objects.get(preferred_username=username, domain=domain)
        logger.debug("Found LocalActor: %s", actor)
    except LocalActor.DoesNotExist:
        logger.error("No actor found for username: %s, domain: %s", username, domain)
        return JsonResponse({'error': 'no actor by that name'}, status=404)

    # Generate HTTPS-based profile and endpoint URLs
    profile_url = f"https://{domain}{reverse('activitypub-profile', kwargs={'username': actor.preferred_username})}"
    followers_url = f"{profile_url}followers/"
    outbox_url = f"{profile_url}outbox/"
    inbox_url = f"{profile_url}inbox/"
    
    # Base WebFinger response with required links
    data = {
        'subject': f'acct:{actor.preferred_username}@{actor.domain}',
        'aliases': [
            profile_url,  # Add alias for actor's profile page
            f"https://{domain}/@{actor.preferred_username}"  # Commonly expected format
        ],
        'links': [
            {
                'rel': 'self',
                'type': 'application/activity+json',
                'href': profile_url,
            },
            {
                'rel': 'http://webfinger.net/rel/profile-page',
                'type': 'text/html',
                'href': f"https://{domain}/@{actor.preferred_username}"  # HTML profile
            },
            {
                'rel': 'followers',
                'type': 'application/activity+json',
                'href': followers_url,
            },
            {
                'rel': 'outbox',
                'type': 'application/activity+json',
                'href': outbox_url,
            },
            {
                'rel': 'inbox',
                'type': 'application/activity+json',
                'href': inbox_url,
            }
        ]
    }

    # Optional icon/avatar support for WebFinger
    if actor.icon:
        icon_url = f"https://{domain}{actor.icon.url}"
        logger.debug("Actor icon URL: %s", icon_url)
        data['links'].append({
            'rel': 'http://webfinger.net/rel/avatar',
            'type': 'image/jpeg',  # Adjust as needed based on your file type
            'href': icon_url,
        })

    # Additional logging for final WebFinger data structure
    logger.debug("WebFinger response data: %s", json.dumps(data, indent=2))
    return JsonResponse(data, content_type="application/jrd+json")



def profile(request, username):
    try:
        actor = LocalActor.objects.get(preferred_username=username)
    except LocalActor.DoesNotExist:
        return JsonResponse({}, status=404)

    actor_type = ActorChoices(actor.actor_type).label

    # Add required context for Lemmy compatibility
    data = {
        '@context': [
            'https://www.w3.org/ns/activitystreams',
            'https://w3id.org/security/v1',
            'https://join-lemmy.org/context.json'  # Lemmy context
        ],
        'type': actor_type,
        'discoverable': True,
        'preferredUsername': actor.preferred_username,
        'id': request.build_absolute_uri(reverse('activitypub-profile', kwargs={'username': actor.preferred_username})).replace("http://", "https://"),
        'followers': request.build_absolute_uri(reverse('activitypub-followers', kwargs={'username': actor.preferred_username})).replace("http://", "https://"),
        'inbox': request.build_absolute_uri(reverse('activitypub-inbox', kwargs={'username': actor.preferred_username})).replace("http://", "https://"),
        'outbox': request.build_absolute_uri(reverse('activitypub-outbox', kwargs={'username': actor.preferred_username})).replace("http://", "https://"),
        'publicKey': {
            'id': request.build_absolute_uri(reverse('activitypub-profile', kwargs={'username': actor.preferred_username})).replace("http://", "https://") + '#main-key',
            'owner': request.build_absolute_uri(reverse('activitypub-profile', kwargs={'username': actor.preferred_username})).replace("http://", "https://"),
            'publicKeyPem': actor.public_key,
        }
    }

    # Ensure name and summary are included, particularly for community actor types
    data['name'] = actor.name if actor.name else "Community Actor Name"  # Default if name is empty
    data['summary'] = actor.summary if actor.summary else "A brief description of the community actor"  # Default if summary is empty

    # Add optional icon and image
    if actor.icon:
        data['icon'] = {
            'type': 'Image',
            'mediaType': 'image/jpeg',  # Make this dynamic if needed
            'url': request.build_absolute_uri(actor.icon.url),
        }
    if actor.image:
        data['image'] = {
            'type': 'Image',
            'mediaType': 'image/jpeg',  # Make this dynamic if needed
            'url': request.build_absolute_uri(actor.image.url),
        }

    # Specifically handle community actors by setting the type to "Group"
    if actor.actor_type == ActorChoices.COMMUNITY:
        data['type'] = 'Group'  # Sets type for ActivityPub compatibility with community actors

    return JsonResponse(data, content_type="application/activity+json")

def community_profile(request, community_name):
    try:
        # Fetch the community actor by name (use the field that stores community names)
        actor = LocalActor.objects.get(preferred_username=community_name, actor_type="community")
    except LocalActor.DoesNotExist:
        return JsonResponse({"error": "Community not found"}, status=404)

    # Build ActivityPub-compatible response for community actor
    data = {
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            "https://w3id.org/security/v1",
            "https://join-lemmy.org/context.json"  # Lemmy-specific context
        ],
        "type": "Group",  # Set type to "Group" for communities
        "discoverable": True,
        "preferredUsername": actor.preferred_username,
        "id": request.build_absolute_uri(reverse("community_detail", kwargs={"community_name": community_name})),
        "followers": request.build_absolute_uri(reverse("community-followers", kwargs={"community_name": community_name})),
        "inbox": request.build_absolute_uri(reverse("community-inbox", kwargs={"community_name": community_name})),
        "outbox": request.build_absolute_uri(reverse("community-outbox", kwargs={"community_name": community_name})),
        "publicKey": {
            "id": request.build_absolute_uri(reverse("community_detail", kwargs={"community_name": community_name})) + "#main-key",
            "owner": request.build_absolute_uri(reverse("community_detail", kwargs={"community_name": community_name})),
            "publicKeyPem": actor.public_key,
        },
        # Basic community metadata
        "name": actor.name or "Community Name",  # Replace with actual community name or a placeholder
        "summary": actor.summary or "A community in the Fediverse",
    }

    # Optional: icon and image URLs
    if actor.icon:
        data["icon"] = {
            "type": "Image",
            "mediaType": "image/jpeg",  # Modify as needed
            "url": request.build_absolute_uri(actor.icon.url),
        }
    if actor.image:
        data["image"] = {
            "type": "Image",
            "mediaType": "image/jpeg",  # Modify as needed
            "url": request.build_absolute_uri(actor.image.url),
        }

    return JsonResponse(data, content_type="application/activity+json")


def followers(request, username):
    logger.debug("Followers request received for username: %s", username)

    try:
        actor = LocalActor.objects.get(preferred_username=username)
        logger.debug("Actor found: %s", actor)
    except LocalActor.DoesNotExist:
        logger.debug("Actor not found for username: %s", username)
        return JsonResponse({}, status=404)

    query = Follower.objects.order_by('-follow_date').select_related('remote_actor').filter(following=actor)
    logger.debug("Followers query executed. Total followers found: %d", query.count())

    paginator = Paginator(query, 10)
    page_num_arg = request.GET.get('page', None)
    followers_url = request.build_absolute_uri(reverse('activitypub-followers', kwargs={'username': actor.preferred_username}))
    logger.debug("Followers URL: %s", followers_url)

    data = {
        '@context': 'https://www.w3.org/ns/activitystreams',
        'type': 'OrderedCollection',
        'totalItems': paginator.count,
        'id': followers_url,
    }
    logger.debug("Initial followers data: %s", json.dumps(data, indent=2))

    if page_num_arg is None:
        data['first'] = followers_url + '?page=1'
        logger.debug("Returning first page link for followers: %s", data['first'])
        return JsonResponse(data, content_type="application/activity+json")

    page_num = int(page_num_arg)
    logger.debug("Requested page number for followers: %d", page_num)

    if 1 <= page_num <= paginator.num_pages:
        page = paginator.page(page_num)
        if page.has_next():
            data['next'] = followers_url + f'?page={page.next_page_number()}'
            logger.debug("Next page link for followers: %s", data['next'])
        data['id'] = followers_url + f'?page={page_num}'
        data['type'] = 'OrderedCollectionPage'
        data['orderedItems'] = [follower.remote_actor.url for follower in page.object_list]
        data['partOf'] = followers_url
        logger.debug("Final followers data for page %d: %s", page_num, json.dumps(data, indent=2))
        return JsonResponse(data, content_type="application/activity+json")
    else:
        logger.debug("Invalid page number requested for followers: %d", page_num)
        return JsonResponse({'error': f'invalid page number: {page_num}'}, status=404)


@csrf_exempt
def community_inbox(request, community_name):
    if request.method == 'POST':
        
        base_uri = 'https://ap.staythepath.lol'  # Set the base URI

        # Parse and handle the POST request for the community
        activity = json.loads(request.body)
        activity_type = activity.get("type")
        
        # Retrieve the community actor (LocalActor)
        try:
            community_actor = LocalActor.objects.get(preferred_username=community_name)
        except LocalActor.DoesNotExist:
            return JsonResponse({"error": "Community not found"}, status=404)
        
        # Handle the "Create" activity (i.e., a new post directed to this community)
        if activity_type == "Create" and "object" in activity:
            post_content = activity["object"].get("content")
            post_author_url = activity["actor"]

            # Log for debugging
            logger.debug(f"Received a post for community '{community_name}' from '{post_author_url}' with content: {post_content}")

            # Fetch the LocalActor instance for person_actor (for 'attributed_to' field)
            try:
                person_actor = LocalActor.objects.get(preferred_username="person_actor")  # Use preferred_username
            except LocalActor.DoesNotExist:
                logger.error(f"Person actor not found.")
                return JsonResponse({"error": "Person actor not found"}, status=404)

            # Create a new post directly using the Note model
            note = Note.objects.create(
                local_actor=community_actor,  # The community actor receiving the post
                content=post_content,
                content_url=f'{base_uri}/pub/{post_author_url}/{uuid.uuid4()}',

                attributed_to=person_actor  # Assign the LocalActor instance to attributed_to
            )

            # Prepare "Create" activity to be sent to the Lemmy community inbox
            create_activity = {
                "@context": ["https://www.w3.org/ns/activitystreams", "https://w3id.org/security/v1"],
                "type": "Create",
                "actor": community_actor.account_url,  # Use the community actor's account URL
                "to": [community_actor.account_url, "https://www.w3.org/ns/activitystreams#Public"],
                "cc": [f"{community_actor.account_url}/followers"],
                "object": {
                    "type": "Page",
                    "id": f"{base_uri}/post/{note.id}",  # Use the Note ID for the post URL
                    "attributedTo": person_actor.account_url,  # Corrected to use the person_actor's account_url
                    "to": [community_actor.account_url, "https://www.w3.org/ns/activitystreams#Public"],
                    "audience": community_actor.account_url,
                    "name": title,
                    "content": f"<p>{message}</p>",
                    "mediaType": "text/html",
                    "source": {
                        "content": message,
                        "mediaType": "text/markdown"
                    },
                    "sensitive": False,
                    "commentsEnabled": True,
                    "published": note.published_at.isoformat(),
                    "updated": note.updated_at.isoformat() if note.updated_at else None
                }
            }
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
################################LOOOOOOOOOOOOOOOOOOOOOOK HHHHHHHHHEEEEEEEEEEEEEEEERRRRRRRRRRRREEEEEEEEEE###########################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
###################################################################################################################################
            # Send "Create" activity to the dynamically defined Lemmy community inbox
            self.send_to_community_inbox(create_activity, community_inbox=community_inbox)

            return JsonResponse({
                'message': "Post successfully created and sent to Lemmy community.",
                'content_url': create_activity["object"]["id"]
            })



@csrf_exempt
def inbox(request, username):
    logger.debug("Custom Library in Use: ConfirmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmmMMmMMMMmmmMMMMMMMMMmmmmmmmmed")

    response = {}

    if request.method == 'POST':
        # Log the raw request and activity type
        logger.debug("Received POST request to inbox for username: %s", username)
        logger.debug("Request body: %s", request.body)

        try:
            activity = json.loads(request.body)
            logger.debug("Parsed Activity: %s", json.dumps(activity, indent=2))
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON: %s", e)
            return JsonResponse({'error': 'Invalid JSON format'}, status=400)

        try:
            actor = LocalActor.objects.get(preferred_username=username)
            logger.debug("Local Actor found for inbox: %s", actor)
        except LocalActor.DoesNotExist:
            logger.error("Local Actor not found for username: %s", username)
            return JsonResponse({'error': 'Local actor not found'}, status=404)

        if activity.get('type') == 'Accept':
            logger.debug("Processing Accept activity")

            accept_object = activity.get('object')
            if not accept_object:
                logger.error("No 'object' in Accept activity")
                return JsonResponse({'error': 'No object in Accept activity'}, status=400)

            if accept_object.get('type') == 'Follow':
                try:
                    remote_actor_url = accept_object.get('object')
                    logger.debug("Looking up Remote Actor with URL: %s", remote_actor_url)
                    
                    try:
                        remote_actor = RemoteActor.objects.get(url=remote_actor_url)
                        logger.debug("Found Remote Actor Object: %s", remote_actor)
                    except RemoteActor.DoesNotExist:
                        logger.error("RemoteActor not found for URL: %s", remote_actor_url)
                        return JsonResponse({'error': 'Remote actor not found'}, status=400)

                    try:
                        follower_entry = Follower.objects.get(remote_actor=remote_actor, following=actor)
                        logger.debug("Found follower entry: %s is following %s", remote_actor, actor)
                    except Follower.DoesNotExist:
                        logger.error("No matching follow request found for Accept activity.")
                        return JsonResponse({'error': 'No matching follow request found'}, status=400)

                    # Return success response for the Accept activity
                    logger.debug("Accept activity processed successfully for actor: %s", actor)
                    return JsonResponse({'ok': True}, status=200)

                except Exception as e:
                    logger.error("Unexpected error in Accept processing: %s", e)
                    return JsonResponse({'error': f'Unexpected error: {e}'}, status=400)
            else:
                logger.error("Invalid Accept activity object type: %s", accept_object.get('type'))
                return JsonResponse({'error': 'Invalid Accept object type'}, status=400)

        elif activity.get('type') == 'Follow':
            logger.debug("Processing a Follow request.")

            # Validate that the 'object' matches the actor
            local_actor = LocalActor.objects.get_by_url(activity['object'])
            if local_actor.id != actor.id:
                logger.debug("Follow object does not match actor. Object: %s, Actor: %s", activity["object"], actor)
                return JsonResponse({'error': f'follow object does not match actor: {activity["object"]}'}, status=400)

            # Attempt to find or create a remote actor
            remote_actor, created = RemoteActor.objects.get_or_create_with_url(url=activity['actor'])
            logger.debug("Remote actor %s: %s", "created" if created else "found", remote_actor)

            # Create a follower record
            Follower.objects.get_or_create(
                remote_actor=remote_actor,
                following=actor,
            )
            logger.debug("Follower created: %s is now following %s", remote_actor, actor)

            # Prepare and send the Accept activity
            accept_data = {
                '@context': [
                    'https://www.w3.org/ns/activitystreams',
                    'https://w3id.org/security/v1',
                ],
                'id': request.build_absolute_uri(f'/{uuid.uuid4()}'),
                'type': 'Accept',
                'actor': request.build_absolute_uri(reverse('activitypub-profile', kwargs={'username': actor.preferred_username})),
                'object': activity,
            }
            logger.debug("Accept data prepared: %s", accept_data)

            sign_resp = signed_post(
                url=remote_actor.profile.get('inbox'),
                private_key=actor.private_key.encode('utf-8'),
                public_key_url=accept_data['actor'] + '#main-key',
                body=json.dumps(accept_data),
            )
            sign_resp.raise_for_status()
            logger.debug("Accept activity sent successfully. Status: %s", sign_resp.status_code)

            response['ok'] = True

        elif activity.get('type') == 'Like':
            note = get_object_or_404(Note, content_url=activity['object'])
            if not note:
                return JsonResponse({'error': f'like object is not a note: {activity["object"]}'}, status=400)

            remote_actor = RemoteActor.objects.get_or_create_with_url(url=activity['actor'])
            note.likes.add(remote_actor)

            response['ok'] = True

        elif activity.get('type') == 'Announce':
            note = get_object_or_404(Note, content_url=activity['object'])
            if not note:
                return JsonResponse({'error': f'announce object is not a note: {activity["object"]}'}, status=400)

            remote_actor = RemoteActor.objects.get_or_create_with_url(url=activity['actor'])
            note.announces.add(remote_actor)

            response['ok'] = True

        elif activity.get('type') == 'Create':
            base_uri = f'{request.scheme}://{request.get_host()}'
            object_data = activity['object']

            if object_data['id'].startswith(base_uri):
                pass  # There is nothing to do, this is our note
            else:
                note = Note.objects.upsert_remote(base_uri, object_data)
                note.local_actor = actor  # Assign the current actor (recipient) to `local_actor`
                note.save()  # Save the note with `local_actor` updated

            response['ok'] = True

        elif activity.get('type') == 'Undo':
            to_undo = activity['object']
            if to_undo['type'] == 'Follow':
                # Validate the 'object' is the actor
                local_actor = LocalActor.objects.get_by_url(to_undo['object'])
                if local_actor.id != actor.id:
                    return JsonResponse({'error': f'undo follow object does not match actor: {to_undo["object"]}'}, status=400)

                remote_actor = get_object_or_404(RemoteActor, url=to_undo['actor'])
                local_actor.followers.remove(remote_actor)

                response['ok'] = True

            elif to_undo['type'] == 'Like':
                note = get_object_or_404(Note, content_url=to_undo['object'])
                if not note:
                    return JsonResponse({'error': f'undo like object is not a note: {to_undo["object"]}'}, status=400)

                remote_actor = get_object_or_404(RemoteActor, url=to_undo['actor'])
                note.likes.remove(remote_actor)

                response['ok'] = True

            elif to_undo['type'] == 'Announce':
                note = get_object_or_404(Note, content_url=to_undo['object'])
                if not note:
                    return JsonResponse({'error': f'undo announce object is not a note: {to_undo["object"]}'}, status=400)

                remote_actor = get_object_or_404(RemoteActor, url=to_undo['actor'])
                note.announces.remove(remote_actor)

                response['ok'] = True

            else:
                return JsonResponse({'error': f'unsupported undo type: {to_undo["type"]}'}, status=400)

        elif activity.get('type') == 'Delete':
            response['ok'] = True  # TODO: support deletes for notes and actors

        else:
            return JsonResponse({'error': f'unsupported activity type: {activity["type"]}'}, status=400)

        return JsonResponse(response, content_type="application/activity+json")
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def outbox(request, username):
    logger.debug("Outbox request received for username: %s", username)
    
    try:
        actor = LocalActor.objects.get(preferred_username=username)
        logger.debug("Actor found: %s", actor)
    except LocalActor.DoesNotExist:
        logger.debug("Actor not found for username: %s", username)
        return JsonResponse({}, status=404)

    query = Note.objects.order_by('-published_at').filter(local_actor=actor)
    logger.debug("Notes query executed. Total notes found: %d", query.count())

    paginator = Paginator(query, 10)
    page_num_arg = request.GET.get('page', None)
    outbox_url = request.build_absolute_uri(reverse('activitypub-outbox', kwargs={'username': actor.preferred_username}))
    logger.debug("Outbox URL: %s", outbox_url)

    data = {
        '@context': 'https://www.w3.org/ns/activitystreams',
        'type': 'OrderedCollection',
        'totalItems': paginator.count,
        'id': outbox_url,
    }
    logger.debug("Initial outbox data: %s", json.dumps(data, indent=2))

    if page_num_arg is None:
        data['first'] = outbox_url + '?page=1'
        logger.debug("Returning first page link: %s", data['first'])
        return JsonResponse(data, content_type="application/activity+json")

    page_num = int(page_num_arg)
    logger.debug("Requested page number: %d", page_num)

    if 1 <= page_num <= paginator.num_pages:
        page = paginator.page(page_num)
        base_uri = f'{request.scheme}://{request.get_host()}'
        if page.has_next():
            data['next'] = outbox_url + f'?page={page.next_page_number()}'
            logger.debug("Next page link: %s", data['next'])
        data['id'] = outbox_url + f'?page={page_num}'
        data['type'] = 'OrderedCollectionPage'
        data['orderedItems'] = [note.as_json(base_uri) for note in page.object_list]
        data['partOf'] = outbox_url
        logger.debug("Final outbox data for page %d: %s", page_num, json.dumps(data, indent=2))
        return JsonResponse(data, content_type="application/activity+json")
    else:
        logger.debug("Invalid page number requested: %d", page_num)
        return JsonResponse({'error': f'invalid page number: {page_num}'}, status=404)



def validate_post_request(request, activity):
    logger.debug("Here is the request:::::::::::::::::::::::: %s", request)
    #logger.debug("Here is the activity:::::::::::::::::::::::: %s", activity)
    if request.method != 'POST':
        raise Exception('Invalid method')

    if 'actor' not in activity:
        return JsonResponse({'error': f'no actor in activity: {activity}'}, status=400)

    try:
        actor_data = fetch_remote_profile(activity['actor'])
    except WebfingerException as e:
        if e.error.response.status_code == 410 and activity['type'] == 'Delete':
            # special case for deletes, the resulting actor will be gone from the server
            return JsonResponse({}, status=410)
        return JsonResponse({'error': 'validate - error fetching remote profile'}, status=401)

    #logger.debug("Here is the actor_data::::::::::::: %s", actor_data)
    #logger.debug("Here is actor_data.get('publicKey') %s", actor_data.get('publicKey'))


    checker = SignatureChecker(actor_data.get('publicKey'))
    result = checker.validate(
        method=request.method.lower(),
        url=request.build_absolute_uri(),
        headers=request.headers,
        body=request.body,
    )

    if not result.success:
        return JsonResponse({'error': 'invalid signature'}, status=401)

    return None

def handle_undo_follow(to_undo, local_actor):
    """
    Handles 'Undo' activities specifically for 'Follow' actions.
    """
    # Ensure the Undo is specifically for a 'Follow' activity
    if to_undo.get('type') == 'Follow':
        follower_url = to_undo['actor']  # The actor who was following
        follow_target = to_undo['object']  # The community being followed

        # Confirm the follow target matches the local actor's URL
        if follow_target == local_actor.url:
            try:
                remote_actor = RemoteActor.objects.get(url=follower_url)
                local_actor.followers.remove(remote_actor)
                logger.debug(f"Removed follower {remote_actor.username} from {local_actor.preferred_username}")
            except RemoteActor.DoesNotExist:
                logger.warning(f"No follower found with URL: {follower_url}")

class NodeInfo(View):
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
    
class SiteInfo(View):
    def get(self, request, *args, **kwargs):
        # Provide general information about the site for the site info endpoint
        site_data = {
            "site_name": "Your Site Name",          # Customize as needed
            "description": "Your Site Description", # Customize as needed
            "version": "YourVersion",               # Customize version
            # Add any other relevant site data here
        }
        return JsonResponse(site_data, content_type="application/json")




class PostDetail(View):
    def get(self, request, username, pk, *args, **kwargs):
        try:
            # Fetch the Note based on the author's username and the primary key
            post = Note.objects.get(local_actor__preferred_username=username, pk=pk)
            data = {
                "@context": "https://www.w3.org/ns/activitystreams",
                "type": "Note",
                "id": post.content_url,  # Use content_url as the unique identifier
                "content": post.content,
                "published": post.published_at.isoformat(),
                "attributedTo": f"https://ap.staythepath.lol/pub/{username}/",
            }
            return JsonResponse(data, content_type="application/activity+json")
        except Note.DoesNotExist:
            return JsonResponse({"error": "Not Found"}, status=404)


        
@method_decorator(csrf_exempt, name='dispatch')
class SetupGroupActor(View):
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
class SetupServiceActor(View):
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
class SetupCommunityActor(View):
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

class Root(View):
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
    
class FederatedInstances(View):
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
class SetupPersonActor(View):
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
class SendNote(View):
    def post(self, request, *args, **kwargs):
        data = json.loads(request.body)
        username = data.get('username', 'tester')
        message = data.get('message', 'This is a test post content.')
        
        try:
            # Retrieve the user and associated LocalActor
            user = get_user_model().objects.get(username=username)
            local_actor = LocalActor.objects.get(user=user)
        except (get_user_model().DoesNotExist, LocalActor.DoesNotExist):
            return JsonResponse({"error": "User or LocalActor not found"}, status=404)

        # Construct base URI and content URL
        base_uri = 'https://ap.staythepath.lol'
        content_url = f'{base_uri}/pub/{user.username}/{uuid.uuid4()}/'  # Create a unique URL for the post

        # Format the content as HTML for ActivityPub compatibility (e.g., for Mastodon)
        formatted_content = f"<p>{message}</p>"

        # Publish the note (similar to `YourModel.publish` logic)
        note, created = Note.objects.get_or_create(
            local_actor=local_actor,
            content=formatted_content,
            content_url=content_url,
            defaults={'attributed_to': local_actor}
        )

        # If the note was successfully created or retrieved, send it to Mastodon
        if created:
            activity_data = {
                "@context": "https://www.w3.org/ns/activitystreams",
                "type": "Create",
                "id": content_url,
                "actor": local_actor.account_url,
                "object": {
                    "type": "Note",
                    "id": content_url,
                    "attributedTo": local_actor.account_url,
                    "content": formatted_content,
                    "published": note.published_at.isoformat(),
                    "to": ["https://www.w3.org/ns/activitystreams#Public"],
                    "cc": [f"{local_actor.account_url}/followers"]
                }
            }

            # Send signed Create activity to followers (like Mastodon)
            for follower in local_actor.followers.all():
                inbox_url = follower.profile.get('inbox', follower.url + '/inbox')

                response = signed_post(
                    url=inbox_url,
                    private_key=local_actor.private_key.encode('utf-8'),
                    public_key_url=f"{local_actor.account_url}#main-key",
                    body=json.dumps(activity_data),
                )
                if response.status_code != 202:
                    logger.error(f"Failed to send activity to {inbox_url}. Status: {response.status_code}")

            response_data = {'message': "Note was successfully created and published.", 'content_url': content_url}
        else:
            response_data = {'error': "Failed to create or publish the note."}

        return JsonResponse(response_data)



    
@method_decorator(csrf_exempt, name='dispatch')
class SendLemmyPost(View):
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

        # Fetch the LocalActor instance for person_actor (for 'attributed_to' field)
        try:
            person_actor = LocalActor.objects.get(preferred_username="person_actor")  # Ensure this is a LocalActor instance
        except LocalActor.DoesNotExist:
            logger.error(f"Person actor not found.")
            return JsonResponse({"error": "Person actor not found"}, status=404)

        # Create a new post directly using the Note model
        note = Note.objects.create(
            local_actor=local_actor,
            content=message,
            content_url=f'{base_uri}/pub/{username}/{uuid.uuid4()}',  # Create a unique URL for the post
            attributed_to=person_actor  # Assign the LocalActor instance to attributed_to
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
                "id": f"{base_uri}/post/{note.id}",  # Use the Note ID for the post URL
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
                "published": note.published_at.isoformat(),
                "updated": note.updated_at.isoformat() if note.updated_at else None
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
            logger.error(f"Failed to send activity to Lemmy community inbox: {e}")




@method_decorator(csrf_exempt, name='dispatch')
class FollowUser(View):
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
class UnfollowUser(View):
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
class FollowCommunity(View):
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
class CommunityDetail(View):
    def get(self, request, community_name, *args, **kwargs):
        # Fetch the community actor using the community name
        community_actor = get_object_or_404(LocalActor, community_name=community_name)

        data = {
            "id": community_actor.account_url,
            "name": community_actor.name,
            "description": community_actor.community_description,
        }
        return JsonResponse(data)


