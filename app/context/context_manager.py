import dataclasses
from typing import List, Optional

from aiogram import types

from app.context.dialog_manager import DialogManager
from app.context.function_manager import FunctionManager
from app.openai_helpers.chatgpt import DialogMessage
from app.openai_helpers.function_storage import FunctionStorage
from app.storage.db import DB, User


@dataclasses.dataclass
class ContextConfiguration:
    model_name: str

    # long term memory is based on embedding context search
    long_term_memory_tokens: int
    # short term memory is used for storing last messages
    short_term_memory_tokens: int

    summary_length: int

    @staticmethod
    def get_config(model: str):
        if model == 'gpt-3.5-turbo':
            return ContextConfiguration(
                model_name=model,
                long_term_memory_tokens=512,
                short_term_memory_tokens=2560,
                summary_length=512,
            )
        elif model == 'gpt-3.5-turbo-16k':
            return ContextConfiguration(
                model_name=model,
                long_term_memory_tokens=1024,
                short_term_memory_tokens=4096,
                summary_length=1024,
            )
        elif model == 'gpt-4':
            return ContextConfiguration(
                model_name=model,
                long_term_memory_tokens=512,
                short_term_memory_tokens=2048,
                summary_length=1024,
            )
        else:
            raise ValueError(f'Unknown model name: {model}')


class ContextManager:
    def __init__(self, db: DB, user: User, message: types.Message):
        self.db = db
        self.user = user
        self.message = message
        self.dialog_manager = None
        self.function_manager = None

    async def process_dialog(self):
        context_configuration = ContextConfiguration.get_config(self.user.current_model)
        self.dialog_manager = DialogManager(self.db, self.user, context_configuration)
        await self.dialog_manager.process_dialog(self.message)

    async def process_functions(self):
        self.function_manager = FunctionManager(self.db, self.user)
        await self.function_manager.process_functions()

    async def process(self):
        await self.process_dialog()
        await self.process_functions()

    async def add_message(self, dialog_message: DialogMessage, tg_message_id: id) -> List[DialogMessage]:
        dialog_messages = await self.dialog_manager.add_message_to_dialog(dialog_message, tg_message_id)
        return dialog_messages

    async def get_context_messages(self) -> List[DialogMessage]:
        dialog_messages = self.dialog_manager.get_dialog_messages()
        return dialog_messages

    async def get_function_storage(self) -> Optional[FunctionStorage]:
        return self.function_manager.get_function_storage()


async def build_context_manager(db: DB, user: User, message: types.Message) -> ContextManager:
    context_manager = ContextManager(db, user, message)
    await context_manager.process()
    return context_manager
