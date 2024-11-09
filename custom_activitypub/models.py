from django.db import models
from django.contrib.auth import get_user_model
from django_activitypub.models import LocalActor, Note
from django.http import JsonResponse
import json

class YourModel(models.Model):
    author = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name='yourmodel_posts')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def formatted_content(self):
        return f"<p>{self.content}</p>"

    def get_absolute_url(self):
        return f'/pub/{self.author.username}/{self.id}/'




    def publish(self, base_uri, activity_data=None):
        actor, created = LocalActor.objects.get_or_create(
            user=self.author,
            defaults={
                'preferred_username': self.author.username,
                'domain': 'ap.staythepath.lol',
                'name': self.author.username
            }
        )

        if activity_data:
            # For Lemmy, send the entire `activity_data` as content, which Lemmy expects
            Note.objects.upsert(
                base_uri=base_uri,
                local_actor=actor,
                content=json.dumps(activity_data),  # Embed Lemmy data
                content_url=activity_data.get("id", f'{base_uri}{self.get_absolute_url()}')
            )
        else:
            # For Mastodon, post a simpler note without additional `activity_data`
            Note.objects.upsert(
                base_uri=base_uri,
                local_actor=actor,
                content=self.formatted_content(),
                content_url=f'{base_uri}{self.get_absolute_url()}'
            )



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