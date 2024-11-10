import json
import requests
from datetime import timezone

def parse_mentions(content):
    """
    Parse a note's content for mentions and return a generator of mention objects
    """
    from models import RemoteActor  # Import within function to avoid circular dependency
    from django_activitypub.custom_markdown import mention_pattern

    mentioned = {}
    for m in mention_pattern.finditer(content):
        key = (m.group('username'), m.group('domain'))
        if key in mentioned:
            continue
        actor = RemoteActor.objects.get_or_create_with_username_domain(*key)
        yield {
            'type': 'Mention',
            'href': actor.url,
            'name': f'{key[0]}@{key[1]}',
        }


def format_datetime(time):
    return time.strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_datetime(time_string):
    try:
        # First, try to parse with microseconds
        return timezone.datetime.strptime(time_string, '%Y-%m-%dT%H:%M:%S.%fZ')
    except ValueError:
        # Fallback to parsing without microseconds if the first format fails
        return timezone.datetime.strptime(time_string, '%Y-%m-%dT%H:%M:%SZ')


def send_create_note_to_followers(base_url, note):
    from models import RemoteActor  # Import within function to avoid circular dependency
    from signed_requests import signed_post
    import uuid

    actor_url = f'{base_url}{note.local_actor.get_absolute_url()}'
    create_msg = {
        '@context': [
            'https://www.w3.org/ns/activitystreams',
            'https://w3id.org/security/v1'
        ],
        'type': 'Create',
        'id': f'{base_url}/{uuid.uuid4()}',
        'actor': actor_url,
        'object': note.as_json(base_url)
    }

    for follower in note.local_actor.followers.all():
        resp = signed_post(
            follower.profile.get('inbox'),
            note.local_actor.private_key.encode('utf-8'),
            f'{actor_url}#main-key',
            body=json.dumps(create_msg)
        )
        resp.raise_for_status()


def send_update_note_to_followers(base_url, note):
    from signed_requests import signed_post  # Import within function to avoid circular dependency

    actor_url = f'{base_url}{note.local_actor.get_absolute_url()}'
    update_msg = {
        '@context': [
            'https://www.w3.org/ns/activitystreams',
        ],
        'type': 'Update',
        'id': f'{note.content_url}#updates/{note.updated_at.timestamp()}',
        'actor': actor_url,
        'object': note.as_json(base_url),
        'published': format_datetime(note.published_at),
    }

    for follower in note.local_actor.followers.all():
        resp = signed_post(
            follower.profile.get('inbox'),
            note.local_actor.private_key.encode('utf-8'),
            f'{actor_url}#main-key',
            body=json.dumps(update_msg)
        )
        resp.raise_for_status()


def send_delete_note_to_followers(base_url, note):
    from signed_requests import signed_post  # Import within function to avoid circular dependency

    actor_url = f'{base_url}{note.local_actor.get_absolute_url()}'
    delete_msg = {
        '@context': [
            'https://www.w3.org/ns/activitystreams',
        ],
        'type': 'Delete',
        'actor': actor_url,
        'object': {
            'id': note.content_url,
            'type': 'Tombstone',
        },
    }

    for follower in note.local_actor.followers.all():
        resp = signed_post(
            follower.profile.get('inbox'),
            note.local_actor.private_key.encode('utf-8'),
            f'{actor_url}#main-key',
            body=json.dumps(delete_msg)
        )
        resp.raise_for_status()


def get_object(url):
    resp = requests.get(url, headers={'Accept': 'application/activity+json'})
    resp.raise_for_status()
    return resp.json()
