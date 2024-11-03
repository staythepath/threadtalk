from django.shortcuts import render
from django.views.generic.detail import DetailView
from .models import YourModel  # Import your model

class YourModelDetailView(DetailView):
    model = YourModel
    template_name = 'yourmodel_detail.html'  # Adjust this path to match your template structure
    context_object_name = 'yourmodel'
