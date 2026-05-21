from aiogram.fsm.state import State, StatesGroup


class ImportCsvStates(StatesGroup):
    awaiting_file = State()
    awaiting_confirm = State()
