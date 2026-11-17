from hmac import compare_digest

from fastapi import FastAPI
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.requests import Request

from app.config import Settings
from app.models import GitlabProject, GitLabEvent, GitlabUser, TelegramAdmin, TelegramGroup, WebhookSecret


class AdminAuth(AuthenticationBackend):
    def __init__(self, settings: Settings):
        super().__init__(secret_key=settings.secret_key)
        self.settings = settings

    async def login(self, request: Request) -> bool:
        form = await request.form()
        username_ok = compare_digest(str(form.get("username", "")).encode(), self.settings.admin_username.encode())
        password_ok = compare_digest(str(form.get("password", "")).encode(), self.settings.admin_password.encode())
        if username_ok and password_ok:
            request.session.update({"admin": True})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("admin"))


class GitlabProjectAdmin(ModelView, model=GitlabProject):
    name = "Project"
    name_plural = "Projects"
    column_list = [
        GitlabProject.name,
        GitlabProject.telegram_group,
        GitlabProject.show_user,
        GitlabProject.show_branch,
        GitlabProject.show_project,
        GitlabProject.show_duration,
        GitlabProject.show_status,
    ]
    column_searchable_list = [GitlabProject.name]
    form_excluded_columns = [GitlabProject.events]


class GitlabUserAdmin(ModelView, model=GitlabUser):
    name = "Gitlab User"
    name_plural = "Gitlab Users"
    column_list = [GitlabUser.gitlab_id, GitlabUser.gitlab_username, GitlabUser.telegram_id]
    column_searchable_list = [GitlabUser.gitlab_username]


class GitLabEventAdmin(ModelView, model=GitLabEvent):
    name = "Event"
    name_plural = "Events"
    column_list = [
        GitLabEvent.gitlab_event,
        GitLabEvent.project,
        GitLabEvent.user_name,
        GitLabEvent.status,
        GitLabEvent.created_at,
    ]
    column_default_sort = [(GitLabEvent.created_at, True)]
    can_create = False
    can_edit = False


class TelegramAdminAdmin(ModelView, model=TelegramAdmin):
    name = "Telegram Admin"
    name_plural = "Telegram Admins"
    column_list = [TelegramAdmin.telegram_id, TelegramAdmin.full_name, TelegramAdmin.username, TelegramAdmin.created_at]


class TelegramGroupAdmin(ModelView, model=TelegramGroup):
    name = "Telegram Group"
    name_plural = "Telegram Groups"
    column_list = [
        TelegramGroup.chat_id,
        TelegramGroup.chat_name,
        TelegramGroup.chat_type,
        TelegramGroup.message_thread_id,
        TelegramGroup.message_thread_name,
        TelegramGroup.is_active,
        TelegramGroup.registered_at,
    ]
    column_searchable_list = [TelegramGroup.chat_name, TelegramGroup.username]


class WebhookSecretAdmin(ModelView, model=WebhookSecret):
    name = "Webhook Signing Token"
    name_plural = "Webhook Signing Tokens"
    column_list = [WebhookSecret.name, WebhookSecret.is_active, WebhookSecret.created_at]
    form_excluded_columns = [WebhookSecret.created_at]
    form_args = {"token": {"description": "Signing token из GitLab (Settings → Webhooks), вида whsec_..."}}


def setup_admin(app: FastAPI, engine: AsyncEngine, settings: Settings) -> None:
    admin = Admin(app, engine, authentication_backend=AdminAuth(settings), title="GitLab Event Bot")
    for view in (GitlabProjectAdmin, GitlabUserAdmin, GitLabEventAdmin, TelegramAdminAdmin, TelegramGroupAdmin,
                 WebhookSecretAdmin):
        admin.add_view(view)
