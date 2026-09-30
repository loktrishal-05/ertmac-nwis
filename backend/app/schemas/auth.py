"""Auth contracts. extra='forbid' on the request rejects any attempt to
supply an identity/role/approver field the server must derive itself."""
from uuid import UUID

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from email_validator import validate_email, EmailNotValidError


def normalized_email(value: str) -> str:
    try:
        return validate_email(value.strip(), check_deliverability=False, allow_smtputf8=False).normalized.lower()
    except EmailNotValidError:
        raise ValueError("Enter a valid email address") from None


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmailInput(Input):
    email: str = Field(min_length=3, max_length=254)
    _email = field_validator("email")(normalized_email)


class SignupRequest(EmailInput):
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128, repr=False)

    @field_validator("display_name")
    @classmethod
    def name(cls, value):
        value = value.strip()
        if not any(c.isalpha() for c in value) or any(ord(c) < 32 for c in value):
            raise ValueError("Name must contain a letter and no control characters")
        return value


class CodeRequest(Input):
    email: str | None = Field(default=None, max_length=254)
    username: str | None = Field(default=None, min_length=1, max_length=100)
    code: str = Field(pattern=r"^[0-9]{6}$", repr=False)

    @model_validator(mode="after")
    def identifier(self):
        if (self.email is None) == (self.username is None):
            raise ValueError("Supply exactly one account identifier")
        if self.email is not None:
            self.email = normalized_email(self.email)
        return self


class ResetRequest(Input):
    reset_token: str = Field(min_length=40, max_length=128, repr=False)
    new_password: str = Field(min_length=12, max_length=128, repr=False)


class AdminCreate(Input):
    username: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=254)
    password: str = Field(min_length=12, max_length=128, repr=False)
    role: Literal["requester", "reviewer", "admin"] = "requester"
    _name = field_validator("display_name")(SignupRequest.name.__func__)

    @model_validator(mode="after")
    def account(self):
        if self.email is not None:
            self.email = normalized_email(self.email)
        if not self.email and not self.username:
            raise ValueError("Email or username is required")
        return self


class RoleRequest(Input):
    role: Literal["requester", "reviewer", "admin"]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=255, repr=False)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    username: str
    role: str
    display_name: str | None = None
    email: str | None = None
    email_verified_at: datetime | None = None
    is_active: bool = True
    signup_pending: bool = False
