from django.urls import path

from .views import ContactCsrfView, ContactMessageView

urlpatterns = [
    path("csrf/", ContactCsrfView.as_view(), name="contact-csrf"),
    path("messages/", ContactMessageView.as_view(), name="contact-message"),
]
