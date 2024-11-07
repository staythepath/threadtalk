import json
import os
import django
from django.urls import reverse
from django.utils import timezone
import argparse
from django_activitypub.signed_requests import signed_post  # Import signed_post
import requests

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_main.settings')
django.setup()

# Import necessary models
from custom_activitypub.models import YourModel
from django_activitypub.models import LocalActor, Note, RemoteActor, Follower
from django.contrib.auth import get_user_model
from django_activitypub.webfinger import finger, WebfingerException, fetch_remote_profile
import logging
import urllib
import uuid
import re

logger = logging.getLogger(__name__)




###########################################################################################################################
################################################## SETUP ##################################################################
###########################################################################################################################

def setup_service_actor():
    """
    Set up or retrieve an existing service actor for testing.
    """
    user, created = get_user_model().objects.get_or_create(username='tester', defaults={'password': 'testpassword'})
    actor, actor_created = LocalActor.objects.get_or_create(
        user=user,
        defaults={
            'preferred_username': 'tester',
            'domain': 'ap.staythepath.lol',
            'name': 'Service Actor',
            'actor_type': 'S'  # 'S' denotes a Service actor
        }
    )
    base_uri = 'https://ap.staythepath.lol'
    return user, actor, base_uri

def get_tester_actor(username='user_tester'):
    """
    Retrieve the existing user and actor based on the specified username.
    """
    user = get_user_model().objects.get(username=username)
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
        content='Wait, we arent sending double, are we?ddddddddddddddddddddddddddddddddddddddddddddddddd.'
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


def follow_user(local_actor_username, remote_actor_handle):
    # Ensure handle format is correct, either "@username@domain" or "username@domain"
    if remote_actor_handle.startswith("@"):
        remote_actor_handle = remote_actor_handle[1:]  # Remove leading "@" if present
    
    # Split the handle into username and domain
    try:
        username, domain = remote_actor_handle.split('@')
    except ValueError:
        raise ValueError("Invalid handle format. Expected format: username@domain or @username@domain")

    # Perform WebFinger lookup
    try:
        webfinger_data = finger(username, domain)
        profile_data = webfinger_data.get("profile")
        
        remote_actor_url = profile_data.get("id")
        inbox_url = profile_data.get("inbox")
        
        # Ensure the URLs are logged for verification
        print(f"Remote Actor URL: {remote_actor_url}")
        print(f"Remote Inbox URL: {inbox_url}")

    except Exception as e:
        print("WebFinger lookup failed:", e)
        return

    # Get the local actor
    local_actor = LocalActor.objects.get(preferred_username=local_actor_username)
    print(f"Local Actor URL: {local_actor.account_url}")

    # Construct the Follow activity with explicit actor-object assignment
    follow_activity = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": f"https://{local_actor.domain}/{uuid.uuid4()}",
        "type": "Follow",
        "actor": local_actor.account_url,   # Ensuring this is the local actor
        "object": remote_actor_url          # Ensuring this is the remote actor
    }
    print("Follow Activity:", follow_activity)

    # Send Follow to the correct inbox
    response = signed_post(
        url=inbox_url,
        private_key=local_actor.private_key.encode('utf-8'),
        public_key_url=f"{local_actor.account_url}#main-key",
        body=json.dumps(follow_activity)
    )
    if response.status_code == 202:
        print(f"Successfully followed {remote_actor_handle}")
    else:
        print(f"Failed to follow: {response.status_code} {response.text}")




###########################################################################################################################
################################################## UNFOLLOW ###############################################################
###########################################################################################################################

def unfollow_user(local_actor_username, remote_actor_url):
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
################################################## SEND LEMMY POST ########################################################
###########################################################################################################################

def fetch_community_id(community_url):
    """
    Fetch the community ID from Lemmy using the community name in the URL.
    """
    import re

    # Extract community name from the URL (e.g., "materialdesign" from "https://lemdro.id/c/materialdesign")
    match = re.search(r'/c/([^/]+)', community_url)
    if not match:
        print("Error: Community name not found in URL.")
        return None
    community_name = match.group(1)

    # Query the Lemmy API to get the community details
    api_url = f"{community_url.split('/c/')[0]}/api/v3/community?name={community_name}"
    response = requests.get(api_url)
    
    if response.status_code == 200:
        community_data = response.json()
        
        # Extract the ID from the nested structure
        try:
            community_id = community_data["community_view"]["community"]["id"]
            print(f"Community ID: {community_id}")  # Debug print to confirm extraction
            return community_id
        except KeyError:
            print(f"Unexpected response structure: {community_data}")
            return None
    else:
        print(f"Failed to fetch community ID: {response.status_code} {response.text}")
        return None


def send_lemmy_post(user, base_uri, actor, community_inbox_url):
    """
    Send a post to a Lemmy community, retrieving community_id dynamically.
    """

    # Fetch the community_id from Lemmy
    community_id = fetch_community_id(community_inbox_url)
    if not community_id:
        print("Unable to retrieve community ID. Exiting.")
        return

    # Construct the post content
    form = {
        "community_id": community_id,
        "name": "Test Post Title",
        "body": "This is a test post from person_user to the materialdesign community.",
        "language_id": 1,
        "nsfw": False,
        "url": "https://example.com"
    }

    # Define the posting URL
    post_url = f"{community_inbox_url.split('/c/')[0]}/api/v3/post"

    # Send the post
    try:
        response = requests.post(post_url, json=form, timeout=30)
        
        # Output result
        if response.status_code == 200:
            print("Post created successfully on Lemmy!")
        else:
            print(f"Failed to post to Lemmy community: {response.status_code} {response.text}")

    except Exception as e:
        print(f"Error posting to Lemmy: {e}")

###########################################################################################################################
################################################## SETUP COMMUNITY ACTOR ##################################################
def setup_community_actor(community_name, community_description):
    """
    Set up or retrieve an existing community actor with the specified name and description.
    """
    # Retrieve or create the user who will 'own' the community
    user, created = get_user_model().objects.get_or_create(
        username='community_admin', defaults={'password': 'adminpassword'}
    )

    # Define a unique preferred username based on the community name
    preferred_username = community_name.lower().replace(" ", "_")

    # Create or retrieve a community actor with the specified name and description
    community_actor, actor_created = LocalActor.objects.get_or_create(
        user=user,
        preferred_username=preferred_username,
        defaults={
            'actor_type': 'C',  # Use 'C' if Community is the intended type
            'domain': 'ap.staythepath.lol',
            'name': community_name,
            'summary': community_description,
            'community_name': community_name,
            'community_description': community_description,
            'inbox': f"https://ap.staythepath.lol/c/{preferred_username}/inbox",
            'outbox': f"https://ap.staythepath.lol/c/{preferred_username}/outbox",
        }
    )

    # If community already exists, update fields to ensure URLs are correct
    if not actor_created:
        community_actor.community_name = community_name
        community_actor.community_description = community_description
        community_actor.inbox = f"https://ap.staythepath.lol/c/{preferred_username}/inbox"
        community_actor.outbox = f"https://ap.staythepath.lol/c/{preferred_username}/outbox"
        community_actor.save()

    print(f"Created or updated community actor: {community_actor.preferred_username} with name '{community_name}' and description '{community_description}'")

    # Notify lemdro.id of the existence of the new community actor
    target_inbox = "https://lemdro.id/inbox"  # Replace with the actual target inbox URL if known

    # Construct the Announce activity
    announce_activity = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": f"https://ap.staythepath.lol/{uuid.uuid4()}",
        "type": "Announce",
        "actor": community_actor.account_url,
        "object": community_actor.account_url  # Announcing the community actor's own URL
    }

    # Send the Announce activity to the target inbox
    response = signed_post(
        url=target_inbox,
        private_key=community_actor.private_key.encode('utf-8'),
        public_key_url=f"{community_actor.account_url}#main-key",
        body=json.dumps(announce_activity)
    )

    # Check the response status
    if response.status_code in (200, 201, 202):
        print(f"Successfully notified {target_inbox} with Announce activity")
    else:
        print(f"Failed to notify: {response.status_code} {response.text}")



###########################################################################################################################
################################################## RUN FUNCTIONS ##########################################################
###########################################################################################################################

# Main block with function execution based on command-line arguments
if __name__ == "__main__":
    # Set up argument parser with available functions and optional parameters
    parser = argparse.ArgumentParser(description="Run specific tests or actions.")
    parser.add_argument("function", choices=[
        "setup_service_actor", "get_tester_actor", "receive_post_test",
        "send_post", "print_inbox_messages", "print_outbox_messages",
        "print_all_notes", "follow_user", "unfollow_user", "delete_all_followed_users",
        "send_lemmy_post", "setup_community_actor"
    ], help="Specify the function to run")
    parser.add_argument("--username", help="Specify the username to use for the function", default="person_user")
    parser.add_argument("--community_name", help="Specify the name of the community", default="Example Community")
    parser.add_argument("--community_description", help="Specify the description of the community", default="A test community.")
    args = parser.parse_args()

    # Utility function to run selected function with appropriate arguments
    def run_function(func_name):
        try:
            if func_name == "setup_service_actor":
                setup_service_actor()
            elif func_name == "get_tester_actor":
                get_tester_actor(username=args.username)
            elif func_name == "setup_community_actor":
                setup_community_actor(args.community_name, args.community_description)
            elif func_name == "receive_post_test":
                receive_post_test(actor_service, base_uri_service)
            elif func_name == "send_post":
                send_post(user_tester, base_uri_tester)
            elif func_name == "print_inbox_messages":
                print_inbox_messages(actor_tester)
            elif func_name == "print_outbox_messages":
                print_outbox_messages(actor_tester)
            elif func_name == "print_all_notes":
                print_all_notes()
            elif func_name == "follow_user":
                follow_user(args.username, "@staythepath@mstdn.social")
            elif func_name == "unfollow_user":
                unfollow_user(args.username, "https://mstdn.social/users/staythepath")
            elif func_name == "delete_all_followed_users":
                delete_all_followed_users(actor_tester)
            elif func_name == "send_lemmy_post":
                send_lemmy_post(user_tester, base_uri_tester, actor_tester, "https://lemdro.id/c/materialdesign")
        except Exception as e:
            print(f"An error occurred while executing {func_name}: {e}")

    # Set up required initial actors and base URIs for testing
    try:
        user_tester, actor_tester, base_uri_tester = get_tester_actor(username=args.username)
        print(f"Retrieved user: {user_tester}, actor: {actor_tester}, base URI: {base_uri_tester}")
        user_service, actor_service, base_uri_service = setup_service_actor()
    except Exception as e:
        print(f"Error during setup: {e}")
        exit(1)

    # Execute the specified function
    run_function(args.function)
