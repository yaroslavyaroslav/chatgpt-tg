import datetime
from typing import List

import settings
from app.bot.utils import message_is_forward
from app.openai_helpers.chatgpt import DialogMessage, summarize_messages
from app.openai_helpers.count_tokens import count_prompt_tokens
from app.storage.db import User, DB, Message

from aiogram import types


class DialogManager:
    """
    Default dialog manager which uses Dialog object to manage dialog messages and supports subdialogs
    """
    def __init__(self, db: DB, user: User):
        self.db = db
        self.user = user
        self.dialog_id = None
        self.dialog_messages = None
        self.is_subdialog = False
        self.chat_id = None

    async def process_main_dialog(self, message: types.Message) -> List[DialogMessage]:
        dialog = await self.db.get_active_dialog(self.user.id)
        if dialog is None:
            dialog = await self.db.create_active_dialog(self.user.id, message.chat.id)
        self.dialog_id = dialog.id

        self.dialog_messages = await self.db.get_dialog_messages(self.dialog_id)
        dialog_messages = [d.message for d in self.dialog_messages]
        return dialog_messages

    async def process_sub_dialog(self, message: types.Message) -> List[DialogMessage]:
        reply_message_id = message.reply_to_message.message_id
        self.dialog_messages = await self.db.get_subdialog_messages(self.chat_id, reply_message_id)
        if self.dialog_messages:
            self.dialog_id = self.dialog_messages[0].dialog_id
        dialog_messages = [d.message for d in self.dialog_messages]
        return dialog_messages

    async def process_dialog(self, message: types.Message) -> List[DialogMessage]:
        self.chat_id = message.chat.id

        if message.reply_to_message is not None and not message_is_forward(message):
            self.is_subdialog = True
            return await self.process_sub_dialog(message)
        else:
            return await self.process_main_dialog(message)

    async def add_message_to_dialog(self, dialog_message: DialogMessage, tg_message_id: id) -> List[DialogMessage]:
        dialog_message = await self.db.create_dialog_message(
            self.dialog_id, self.user.id, self.chat_id, tg_message_id,
            dialog_message, self.dialog_messages, self.is_subdialog
        )
        self.dialog_messages.append(dialog_message)
        return self.get_dialog_messages()

    def get_dialog_messages(self) -> List[DialogMessage]:
        if self.dialog_messages is None:
            raise ValueError('You must call process_dialog first')
        dialog_messages = [d.message for d in self.dialog_messages]
        return dialog_messages


class DynamicDialogManager:
    """
    Dialog manager to manage dialog without Dialog object using dynamic dialog building
    """
    def __init__(self, db: DB, user: User, context_configuration):
        self.db = db
        self.user = user
        self.dialog_messages = None
        self.chat_id = None
        self.context_configuration = context_configuration

        # no subdialog mechanism
        self.is_subdialog = False
        # dialog is not needed, so set up stub value
        self.dialog_id = -1

    async def process_dialog(self, message: types.Message) -> List[DialogMessage]:
        self.chat_id = message.chat.id

        if message.reply_to_message is not None and not message_is_forward(message):
            db_message = await self.db.get_telegram_message(self.chat_id, message.reply_to_message.message_id)
        else:
            db_message = await self.db.get_last_message(self.user.id, self.chat_id)

        if not db_message:
            self.dialog_messages = []
            return []

        dialog_messages = await self.db.get_messages_by_ids(db_message.previous_message_ids)
        dialog_messages.append(db_message)

        dialog_messages = self.filter_old_messages(dialog_messages)
        if not dialog_messages:
            self.dialog_messages = []
            return []

        if count_prompt_tokens(m.message for m in dialog_messages) >= self.context_configuration.short_term_memory_tokens:
            to_summarize, to_process = self.split_context_by_token_length(dialog_messages)
            summarized_message = await self.summarize_messages(to_summarize)
            self.dialog_messages = [summarized_message] + to_process
        else:
            self.dialog_messages = dialog_messages
        return self.get_dialog_messages()

    @staticmethod
    def filter_old_messages(messages: List[Message]):
        tz = datetime.datetime.now().astimezone().tzinfo
        time_window = datetime.datetime.now(tz) - datetime.timedelta(seconds=settings.MESSAGE_EXPIRATION_WINDOW)
        return list(filter(lambda m: m.cdate >= time_window, messages))

    def split_context_by_token_length(self, messages: List[Message]):
        token_length = self.context_configuration.short_term_memory_tokens / 2
        for split_point in range(len(messages)):
            right_dialog_messages = (d.message for d in messages[split_point:])
            right_length = count_prompt_tokens(right_dialog_messages)
            if right_length <= token_length:
                return messages[:split_point], messages[split_point:]
        else:
            return messages, []

    async def summarize_messages(self, messages: List[Message]):
        summarized = await summarize_messages([m.message for m in messages], self.user.current_model, self.context_configuration.mid_term_memory_tokens)
        summarized_message = DialogUtils.prepare_user_message(f"Summarized previous conversation:\n{summarized}")
        # TODO: make tg_message_id nullable
        tg_message_id = -1
        message = await self.db.create_dialog_message(
            self.dialog_id, self.user.id, self.chat_id, tg_message_id,
            summarized_message, [], self.is_subdialog
        )
        return message

    async def add_message_to_dialog(self, dialog_message: DialogMessage, tg_message_id: id) -> List[DialogMessage]:
        dialog_message = await self.db.create_dialog_message(
            self.dialog_id, self.user.id, self.chat_id, tg_message_id,
            dialog_message, self.dialog_messages, self.is_subdialog
        )
        self.dialog_messages.append(dialog_message)
        return self.get_dialog_messages()

    def get_dialog_messages(self) -> List[DialogMessage]:
        if self.dialog_messages is None:
            raise ValueError('You must call process_dialog first')
        dialog_messages = [d.message for d in self.dialog_messages]
        return dialog_messages


class DialogUtils:
    @staticmethod
    def prepare_user_message(message_text: str) -> DialogMessage:
        return DialogMessage(role="user", content=message_text)

    @staticmethod
    def prepare_function_response(function_name, function_response):
        return DialogMessage(role="function", name=function_name, content=function_response)
