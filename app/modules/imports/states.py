from aiogram.fsm.state import State, StatesGroup


class ImportCsvStates(StatesGroup):
    awaiting_file = State()
    awaiting_preview = State()
    awaiting_commit = State()