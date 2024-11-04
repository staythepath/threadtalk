import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_main.settings')
django.setup()

from django.contrib.auth import get_user_model
from custom_activitypub.models import YourModel  # Replace 'custom_activitypub' with your app's name

def test_publish_new_user():
    # Get or create a new test user
    User = get_user_model()
    new_user, created = User.objects.get_or_create(username='tester')

    # if created:
    #     print("Created new user: newtestuser.")
    # else:
    #     print("User newtestuser already exists.")

    # Create a new instance of YourModel for the new user
    content = "This is a test post for aNow will this show up??????????????????????????? new user in ActivityPub integration."
    your_model_instance = YourModel.objects.create(author=new_user, content=content)

    # Publish the post
    base_uri = 'https://ap.staythepath.lol/pub/'
    your_model_instance.publish(base_uri=base_uri)

    print(f"Published content with ID: {your_model_instance.id} for {new_user}")

if __name__ == '__main__':
    test_publish_new_user()
