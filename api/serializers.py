
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer




class RegisterSerializer(serializers.ModelSerializer):
    confirm_password = serializers.CharField(write_only=True, required=True)
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],  
    )

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "password",
            "confirm_password",
        ]
        extra_kwargs = {
            "first_name": {"required": True},
            "last_name":  {"required": True},
            "email":      {"required": True},
        }

    # ── Validation ────────────────────────────

    def validate_email(self, value: str) -> str:
        """Email must be unique."""
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    def validate_username(self, value: str) -> str:
        """Username uniqueness is handled by the model, but surface a cleaner message."""
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs

    # ── Create ────────────────────────────────

    def create(self, validated_data: dict) -> User:
        validated_data.pop("confirm_password")
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )
        return user


# ──────────────────────────────────────────────
# 2. Custom JWT claim pair (login)
# ──────────────────────────────────────────────

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extends the default JWT login response to include basic user info
    alongside the access + refresh tokens.

    Response shape:
    {
        "access":     "<JWT>",
        "refresh":    "<JWT>",
        "user": {
            "id":         1,
            "username":   "juandelacruz",
            "first_name": "Juan",
            "last_name":  "dela Cruz",
            "email":      "juan@example.com"
        }
    }
    """

    def validate(self, attrs: dict) -> dict:
        data = super().validate(attrs)          # runs credential check + adds tokens
        data["user"] = {
            "id":         self.user.id,
            "username":   self.user.username,
            "first_name": self.user.first_name,
            "last_name":  self.user.last_name,
            "email":      self.user.email,
        }
        return data


# ──────────────────────────────────────────────
# 3. User read-only (for /api/me/)
# ──────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    """Read-only snapshot of the authenticated user."""

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "date_joined"]
        read_only_fields = fields