from aiogram.fsm.state import State, StatesGroup


class ExportStates(StatesGroup):
    waiting_for_city = State()
    waiting_for_source = State()
