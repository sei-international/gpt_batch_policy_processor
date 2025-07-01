import logging

logger = logging.getLogger("aipolicy")
class StreamlitLogHandler(logging.Handler):
    def __init__(self, placeholder):
        super().__init__()
        self.placeholder = placeholder
        self.buffer = []
    def emit(self, record):
        self.buffer.append(self.format(record))
        self.placeholder.text("\n".join(self.buffer))
def init_logger(placeholder):
    handler = StreamlitLogHandler(placeholder)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)