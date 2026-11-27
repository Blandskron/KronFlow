from django.urls import path

from .views import ContactCsrfView, ContactMessageDsarView, ContactMessageView

urlpatterns = [
    path("csrf/", ContactCsrfView.as_view(), name="contact-csrf"),
    path("messages/", ContactMessageView.as_view(), name="contact-message"),
    path("messages/dsar/", ContactMessageDsarView.as_view(), name="contact-message-dsar"),
]
