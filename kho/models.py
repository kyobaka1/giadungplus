from django.db import models
from django.contrib.auth.models import User

class Warehouse(models.Model):
    code = models.CharField(max_length=20, unique=True)  # 'gele', 'toky'
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    warehouses = models.ManyToManyField(Warehouse, blank=True)
    display_name = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.display_name or self.user.username
