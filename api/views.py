# accounts/views.py

from django.contrib.auth.models import User
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    CustomTokenObtainPairSerializer,
    RegisterSerializer,
    UserSerializer,
)


# ──────────────────────────────────────────────
# 1. Register  →  POST /api/auth/register/
# ──────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    """
    Create a new user account.

    - No authentication required.
    - Validates username uniqueness, email uniqueness, password strength,
      and that password == confirm_password.
    - Returns the new user's public fields (no tokens).
      The client should immediately call POST /api/auth/token/ to log in.

    Request body:
        {
            "username":         "juandelacruz",
            "first_name":       "Juan",
            "last_name":        "dela Cruz",
            "email":            "juan@example.com",
            "password":         "StrongPass123!",
            "confirm_password": "StrongPass123!"
        }

    Success 201:
        {
            "message": "Account created successfully.",
            "user": { "id": 1, "username": "juandelacruz", ... }
        }
    """

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "message": "Account created successfully.",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


# ──────────────────────────────────────────────
# 2. Login (JWT)  →  POST /api/auth/token/
# ──────────────────────────────────────────────

class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Authenticate with username + password.
    Returns access token (30 min), refresh token (1 day), and basic user info.

    Request body:
        { "username": "juandelacruz", "password": "StrongPass123!" }

    Success 200:
        {
            "access":  "<JWT>",
            "refresh": "<JWT>",
            "user": { "id": 1, "username": "...", "email": "..." }
        }
    """

    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]


# ──────────────────────────────────────────────
# 3. Current user  →  GET /api/auth/me/
# ──────────────────────────────────────────────

class MeView(APIView):
    """
    Return the authenticated user's profile.
    Requires a valid access token in the Authorization header:
        Authorization: Bearer <access_token>

    Success 200:
        { "id": 1, "username": "...", "first_name": "...", ... }
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)