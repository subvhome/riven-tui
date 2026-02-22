from textual.message import Message

class RefreshPoster(Message):
    pass

class LogMessage(Message):
    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

class CalendarItemSelected(Message):
    def __init__(self, item_data: dict) -> None:
        super().__init__()
        self.item_data = item_data

class PageChanged(Message):
    def __init__(self, page: int) -> None:
        self.page = page
        super().__init__()

class MonthChanged(Message):
    def __init__(self, year: int, month: int) -> None:
        self.year = year
        self.month = month
        super().__init__()

class ToggleLibrarySelection(Message):
    def __init__(self, item_id: str, title: str) -> None:
        super().__init__()
        self.item_id = item_id
        self.title = title
