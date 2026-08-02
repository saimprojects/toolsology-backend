from django.urls import path
from .views import BlogDetailView, BlogListView

urlpatterns = [
    path("", BlogListView.as_view(), name="blog-list"),
    path("<slug:slug>/", BlogDetailView.as_view(), name="blog-detail"),
]
