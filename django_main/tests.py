import json
import logging
from django.test import TestCase
from django.contrib.auth.models import User
from django_activitypub.models import LocalActor
from django_activitypub.signed_requests import signed_post

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

class ActivityPubTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='thisisit')
        self.actor = LocalActor.objects.create(
            user=self.user,
            name='testuser',
            preferred_username='testuser',
            domain='127.0.0.1:8000'
        )

    def test_signature(self):
        actor_url = f"http://127.0.0.1:8000/pub/{self.actor.preferred_username}"
        url = f"http://127.0.0.1:8000/pub/{self.actor.preferred_username}/inbox"
        message = {
            "type": "Create",
            "actor": actor_url,
            "object": {
                "type": "Note",
                "content": "Hello, ActivityPub!"
            }
        }

        logger.debug("Sending POST request...")
        response = signed_post(
            url=url,
            private_key=self.actor.private_key.encode('utf-8'),
            public_key_url=actor_url + '#main-key',
            body=json.dumps(message)
        )

        logger.debug("Received response: %s", response)

        if response is None:
            self.fail("No response received from signed_post.")
        else:
            logger.debug("Response status code: %s", response.status_code)
            logger.debug("Response headers: %s", response.headers)
            logger.debug("Response body: %s", response.text)

            # Check the response status code
            self.assertNotEqual(response.status_code, 401, "Unauthorized - signature likely invalid")
            self.assertEqual(response.status_code, 200, "Expected successful response but got a different status.")
