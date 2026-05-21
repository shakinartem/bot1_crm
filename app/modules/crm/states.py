from aiogram.fsm.state import State, StatesGroup


class CompanyCreateStates(StatesGroup):
    name = State()
    phone = State()
    website = State()
    city = State()
    notes = State()


class CompanySearchStates(StatesGroup):
    query = State()


class CompanyCallStates(StatesGroup):
    comment = State()


class CompanyNoteStates(StatesGroup):
    text = State()


class DecisionMakerStates(StatesGroup):
    full_name = State()
    role = State()
    phone = State()
    email = State()
    telegram = State()
    notes = State()
    confirm = State()


class ContactPointStates(StatesGroup):
    contact_type = State()
    value = State()
    label = State()
    is_primary = State()


class TaskStates(StatesGroup):
    title = State()
    description = State()
    due_at = State()
