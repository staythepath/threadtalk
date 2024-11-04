from django.http import JsonResponse
from django.views import View
from .models import YourModel

class YourModelDetailView(View):
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
