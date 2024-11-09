import json
import re
import uuid
import urllib.parse

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse, resolve
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from django_activitypub.models import ActorChoices, LocalActor, RemoteActor, Follower, Note
from django_activitypub.signed_requests import signed_post, SignatureChecker
from django_activitypub.webfinger import fetch_remote_profile, WebfingerException
import logging

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
        # Parse and handle the POST request for the community
        activity = json.loads(request.body)
        activity_type = activity.get("type")
        
        # Retrieve the community actor
        try:
            community_actor = LocalActor.objects.get(preferred_username=community_name)

        except LocalActor.DoesNotExist:
            return JsonResponse({"error": "Community not found"}, status=404)
        
        # Handle the "Create" activity (i.e., a new post directed to this community)
        if activity_type == "Create" and "object" in activity:
            post_content = activity["object"].get("content")
            post_author = activity["actor"]

            # Log for debugging
            print(f"Received a post for community '{community_name}' from '{post_author}' with content: {post_content}")

            # Save or process the post here
            # This could involve creating a new Note object or aactornother model to track community posts
            post = Note.objects.create(
                local_actor=community_actor,  # The community actor receiving the post
                content=post_content,
                attributed_to=post_author,
            )

            # Generate an "Announce" activity to notify followers of this community
            announce_activity = {
                "@context": "https://www.w3.org/ns/activitystreams",
                "type": "Announce",
                "actor": community_actor.actor_uri,
                "object": activity["object"]["id"],  # ID of the original post
                "to": f"{community_actor.actor_uri}/followers",  # Announce to followers
            }

            # Log announce activity for debugging
            print(f"Announcing new post for community '{community_name}' to followers.")

            # Send the announce activity to followers (this would be sent over HTTP in a real implementation)
            # Example: send_to_followers(announce_activity)

            return JsonResponse({"status": "Activity received and announced"}, status=200)
        
        # If the activity type is not supported
        return JsonResponse({"error": "Unsupported activity type"}, status=400)
    
    return JsonResponse({"error": "Invalid request"}, status=400)

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


