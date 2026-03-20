# accounts/models.py
#
# We rely entirely on Django's built-in User model.
# It already provides: id, username, first_name, last_name,
# email, password (hashed), is_active, date_joined.
#
# Extend here later if you need extra profile fields, e.g.:
#
#   class Profile(models.Model):
#       user    = models.OneToOneField(User, on_delete=models.CASCADE)
#       avatar  = models.ImageField(upload_to="avatars/", blank=True)
#
# For now — nothing extra needed.

from django.contrib.auth.models import User  # noqa: F401