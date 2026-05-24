from aiogram.fsm.state import State, StatesGroup


class DigestStates(StatesGroup):
    task_snooze_due_at = State()
    settings_time = State()
    settings_stale_days = State()
