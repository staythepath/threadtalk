
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_main.settings')  # Replace with your project settings
django.setup()

import logging
import json
from django_activitypub.models import LocalActor
from django_activitypub.signed_requests import signed_post  # Importing the library function
from django.contrib.auth.models import User
import os

logging.basicConfig(level=logging.DEBUG)

# Main function to run the test
def run_activity_pub_test():
    try:
        # Fetch the existing user
        user = User.objects.get(username='testuser')
        actor = LocalActor.objects.get(user=user)

        # Prepare the data for the ActivityPub request
        actor_url = f"http://127.0.0.1:8000/pub/{actor.preferred_username}"
        url = f"http://127.0.0.1:8000/pub/{actor.preferred_username}/inbox"
        message = {
            "type": "Create",
            "actor": actor_url,
            "object": {
                "type": "Note",
                "content": "Hello, ActivityPub!"
            }
        }

        # Use signed_post to send the request
        response = signed_post(
            url=url,
            private_key=actor.private_key.encode('utf-8'),  # Use the actor's private key
            public_key_url=actor_url + '#main-key',  # Assuming this is the correct public key URL format
            body=json.dumps(message),  # Convert message to JSON string
        )

        # Log the response
        logging.debug(f"Response status code: {response.status_code}")
        logging.debug(f"Response headers: {response.headers}")
        logging.debug(f"Response body: {response.text}")

    except User.DoesNotExist:
        logging.error("User 'testuser' does not exist.")
    except LocalActor.DoesNotExist:
        logging.error("LocalActor for 'testuser' does not exist.")
    except Exception as e:
        logging.error(f"An error occurred: {e}")

# Execute the function
if __name__ == "__main__":
    run_activity_pub_test()
