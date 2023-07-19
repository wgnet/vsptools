from abc import ABCMeta


class TransactionException(Exception, metaclass=ABCMeta):
    def __init__(self, message):
        if message:
            self.message = message
        else:
            self.message = None

    def __str__(self):
        if self.message:
            return f"Exportana. {self.message}"
        else:
            return f"Exportana. {self.__class__.__name__} has been raised"

    def __repr__(self):
        if self.message:
            return f"Exportana. {self.__class__.__name__}, {self.message}"
        else:
            return f"Exportana. {self.__class__.__name__} has been raised"
