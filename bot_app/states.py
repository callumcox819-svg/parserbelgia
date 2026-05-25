from aiogram.fsm.state import State, StatesGroup


class SettingsForm(StatesGroup):
    waiting_json_limit = State()
    waiting_proxy = State()


class AdminForm(StatesGroup):
    waiting_grant_user = State()
    waiting_revoke_user = State()
