"""The part of Telegram's Update object this bot reads."""
from pydantic import BaseModel, ConfigDict, Field


class User(BaseModel):
    id: int


class Chat(BaseModel):
    id: int
    type: str
    title: str | None = None
    username: str | None = None
    is_forum: bool = False


class ForumTopicCreated(BaseModel):
    name: str


class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_id: int
    from_user: User | None = Field(default=None, alias="from")
    chat: Chat
    text: str | None = None
    message_thread_id: int | None = None
    is_topic_message: bool = False
    reply_to_message: "Message | None" = None
    forum_topic_created: ForumTopicCreated | None = None

    @property
    def topic_id(self) -> int | None:
        """The topic of a forum message (message_thread_id is also set for plain replies)."""
        return self.message_thread_id if self.is_topic_message else None


class Update(BaseModel):
    update_id: int
    message: Message | None = None
