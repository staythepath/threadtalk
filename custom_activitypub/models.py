from django.db import models
from django.contrib.auth import get_user_model
from django_activitypub.models import LocalActor, Note

class YourModel(models.Model):
    author = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name='yourmodel_posts')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def formatted_content(self):
        return f"<p>{self.content}</p>"

    def get_absolute_url(self):
        return f'/pub/testuser/{self.id}/'  # Adjust this path to match your actual URL configuration


    def publish(self, base_uri):
        actor, created = LocalActor.objects.get_or_create(user=self.author, defaults={
            'preferred_username': self.author.username,
            'domain': 'localhost'
        })
        Note.objects.upsert(
            base_uri=base_uri,
            local_actor=actor,
            content=self.formatted_content(),
            content_url=f'{base_uri}{self.get_absolute_url()}'
        )
