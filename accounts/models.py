from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

class CustomUser(AbstractUser):
    ROLE_CHOICES = [
        ('viewer', 'Viewer'),
        ('investor', 'Investor'),
        ('admin', 'Admin'),
    ]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='viewer')
    email_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.username
