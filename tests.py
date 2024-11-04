# Load Django shell with your project context
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_main.settings')
django.setup()

# Import necessary models
from custom_activitypub.models import YourModel
from django_activitypub.models import LocalActor
from django.contrib.auth import get_user_model

# Create a user or get an existing one
User = get_user_model()
user, created = User.objects.get_or_create(username='tester', defaults={'password': 'testpassword'})

# Ensure a LocalActor exists for this user
actor, actor_created = LocalActor.objects.get_or_create(
    user=user,
    defaults={
        'preferred_username': 'tester',
        'domain': 'ap.staythepath.lol',
        'name': 'Tester'
    }
)

# Base URI for the test environment
base_uri = 'https://ap.staythepath.lol'

# Create a post
post = YourModel.objects.create(
    author=user,
    content='ITS ALIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIVE!!'
)

# Publish the post
post.publish(base_uri=base_uri)

# Verify that the post has been published
from django_activitypub.models import Note

note = Note.objects.filter(local_actor=actor, content__contains="This is a test message").first()

if note:
    print("Note was successfully created and published.")
    print("Note Content URL:", note.content_url)
else:
    print("Failed to create or publish the note.")
