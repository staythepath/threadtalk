import json
import os
import django
from django.urls import reverse
from django.utils import timezone
from django_activitypub.signed_requests import signed_post  # Import signed_post

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_main.settings')
django.setup()

# Import necessary models
from custom_activitypub.models import YourModel
from django_activitypub.models import LocalActor, Note, RemoteActor, Follower
from django.contrib.auth import get_user_model
from django_activitypub.webfinger import finger, WebfingerException, fetch_remote_profile
import logging

import uuid

logger = logging.getLogger(__name__)




###########################################################################################################################
################################################## SETUP ##################################################################
###########################################################################################################################

def setup_service_actor():
    """
    Set up or retrieve an existing service actor for testing.
    """
    user, created = get_user_model().objects.get_or_create(username='tester2', defaults={'password': 'testpassword'})
    actor, actor_created = LocalActor.objects.get_or_create(
        user=user,
        defaults={
            'preferred_username': 'tester2',
            'domain': 'ap.staythepath.lol',
            'name': 'Service Actor',
            'actor_type': 'S'  # 'S' denotes a Service actor
        }
    )
    base_uri = 'https://ap.staythepath.lol'
    return user, actor, base_uri

def get_tester_actor():
    """
    Retrieve the existing tester user and actor.
    """
    user = get_user_model().objects.get(username='tester2')
    actor = LocalActor.objects.get(user=user)
    return user, actor, 'https://ap.staythepath.lol'

###########################################################################################################################
################################################## RECEIVE A MESSAGE ######################################################
###########################################################################################################################

def receive_post_test(actor, base_uri):
    """
    Simulate receiving a Create activity for the service actor and verify that a Note is created.
    """
    create_activity = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "type": "Create",
        "actor": f"{base_uri}/pub/remote_actor/",
        "object": {
            "type": "Note",
            "id": f"{base_uri}/pub/service_actor/1/",
            "content": "<p>This is a test post for the Service Actor.</p>",
            "published": "2024-11-04T06:00:00Z",
            "attributedTo": f"{base_uri}/pub/remote_actor/",
            "to": ["https://www.w3.org/ns/activitystreams#Public"]
        }
    }

    # Simulate sending a POST request to the service actor's inbox
    from django.test import Client
    client = Client()
    response = client.post(
        reverse('activitypub-inbox', kwargs={'username': 'service_actor'}),
        data=json.dumps(create_activity),
        content_type="application/activity+json"
    )

    # Check response and created note
    print("Response status code:", response.status_code)
    note = Note.objects.filter(local_actor=actor, content__contains="This is a test post for the Service Actor.").first()
    if note:
        print("Note was successfully created.")
    else:
        print("Failed to create Note.")


###########################################################################################################################
################################################## SEND A MESSAGE #########################################################
###########################################################################################################################


def send_post(user, base_uri):
    """
    Send a post on behalf of the tester user.
    """
    post = YourModel.objects.create(
        author=user,
        content='Wait, we arent sending double, are we?.'
    )
    post.publish(base_uri=base_uri)

    # Verify the post creation
    note = Note.objects.filter(local_actor=LocalActor.objects.get(user=user), content__contains="This is a test message").first()
    if note:
        print("Note was successfully created and published.")
        print("Note Content URL:", note.content_url)
    else:
        print("Failed to create or publish the note.")

###########################################################################################################################
################################################## PRINT INBOX MESSAGES ###################################################
###########################################################################################################################

def print_inbox_messages(actor):
    """
    Print all notes received by the specified actor (inbox).
    """
    print("\n--- Inbox Messages (Received) ---\n")
    # Filter notes where `remote_actor` is populated and `local_actor` is the actor, indicating a received message.
    inbox_notes = Note.objects.filter(remote_actor__isnull=False).order_by('-published_at')
    print(f"Here are the inbox notes:::::::::: {inbox_notes}")

    if inbox_notes.exists():
        for idx, note in enumerate(inbox_notes, start=1):
            print(f"Message {idx}:")
            print(f"  Content URL: {note.content_url}")
            print(f"  Local Actor: {note.local_actor}")
            print(f"  Remote Actor: {note.remote_actor}")
            print(f"  Published At: {note.published_at}")
            print(f"  Content: {note.content}")
            print(f"  From: {note.remote_actor.handle if note.remote_actor else 'Unknown'}")
            print("-" * 50)
    else:
        print("No messages found in the inbox.")



###########################################################################################################################
################################################## PRINT OUTBOX MESSAGES ##################################################
###########################################################################################################################

def print_outbox_messages(actor):
    """
    Print all notes sent by the specified actor (outbox messages).
    """
    print("\n--- Outbox Messages (Sent) ---\n")
    outbox_notes = Note.objects.filter(local_actor=actor, remote_actor__isnull=True).order_by('-published_at')

    if outbox_notes.exists():
        for idx, note in enumerate(outbox_notes, start=1):
            print(f"Message {idx}:")
            print(f"  Local Actor: {note.local_actor}")
            print(f"  Remote Actor: {note.remote_actor}")
            print(f"  Content URL: {note.content_url}")
            print(f"  Published At: {note.published_at}")
            print(f"  Content: {note.content}")
            print("  To: Public")  # Assuming most posts are public; this could be more specific if required
            print("-" * 50)
    else:
        print("No messages found in the outbox.")

###########################################################################################################################
################################################## PRINT ALL NOTES ########################################################
###########################################################################################################################

def print_all_notes():
    """
    Print all notes to inspect their local_actor and remote_actor fields.
    """
    all_notes = Note.objects.all()
    for note in all_notes:
        print(f"Note ID: {note.id}")
        print(f"  Content URL: {note.content_url}")
        print(f"  Local Actor: {note.local_actor}")
        print(f"  Remote Actor: {note.remote_actor}")
        print(f"  Content: {note.content}")
        print(f"  Published At: {note.published_at}")
        print("-" * 50)


###########################################################################################################################
################################################## FOLLOW #################################################################
###########################################################################################################################


def follow_user(local_actor_username, remote_actor_url):
        # Fetch or create the remote actor
        remote_actor, _ = RemoteActor.objects.get_or_create_with_url(remote_actor_url)

        # Get the local actor
        local_actor = LocalActor.objects.get(preferred_username=local_actor_username)

        # Construct the Follow activity
        follow_activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "id": f"https://{local_actor.domain}/{uuid.uuid4()}",
            "type": "Follow",
            "actor": local_actor.account_url,
            "object": remote_actor.url
        }

        # Send the Follow activity to the remote actor's inbox
        inbox_url = remote_actor.profile.get('inbox', remote_actor.url + '/inbox')
        response = signed_post(
            url=inbox_url,
            private_key=local_actor.private_key.encode('utf-8'),
            public_key_url=f"{local_actor.account_url}#main-key",
            body=json.dumps(follow_activity)
        )

        if response.status_code == 202:
            print(f"Successfully followed {remote_actor.handle}")
        else:
            print(f"Failed to follow: {response.status_code} {response.text}")

###########################################################################################################################
################################################## UNFOLLOW ###############################################################
###########################################################################################################################

def unfollow_user(self, local_actor_username, remote_actor_url):
    # Fetch the remote actor
    remote_actor = RemoteActor.objects.get(url=remote_actor_url)

    # Get the local actor
    local_actor = LocalActor.objects.get(preferred_username=local_actor_username)

    # Construct the Undo-Follow activity
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

    # Send the Undo activity to the remote actor's inbox
    inbox_url = remote_actor.profile.get('inbox', remote_actor.url + '/inbox')
    response = signed_post(
        url=inbox_url,
        private_key=local_actor.private_key.encode('utf-8'),
        public_key_url=f"{local_actor.account_url}#main-key",
        body=json.dumps(undo_follow_activity)
    )

    if response.status_code == 202:
        print(f"Successfully unfollowed {remote_actor.handle}")
    else:
        print(f"Failed to unfollow: {response.status_code} {response.text}")


###########################################################################################################################
################################################## DELETE ALL FOLLOWS #####################################################
###########################################################################################################################

def delete_all_followed_users(local_actor):
    """
    Deletes all RemoteActors that the specified local_actor is following.
    """
    # Remove all Follower relationships where local_actor is following a remote actor
    Follower.objects.filter(following=local_actor).delete()
    print(f"Deleted all followers of {local_actor}")




###########################################################################################################################
################################################## RUN FUNCTIONS ##########################################################
###########################################################################################################################


# Retrieve actors
#user_tester, actor_tester, base_uri_tester = get_tester_actor()
#User_service, actor_service, base_uri_service = setup_service_actor()

# Uncomment the functions below to run specific tests
# send_post(user_tester, base_uri_tester)   # Send a post for the tester user
# receive_post_test(actor_service, base_uri_service)   # Receive a message for the service actor
#print_inbox_messages(actor_tester)   # Print inbox messages for the tester actor
#print_outbox_messages(actor_tester)  # Print outbox messages for the tester actor
#print_all_notes()
#delete_all_followed_users(actor_tester)

follow_user('tester2', 'https://mstdn.social/users/staythepath')
#unfollow_user('tester', 'https://mstdn.social/users/staythepath')