import logging
from pythonjsonlogger import jsonlogger
from app.middlewares.observability import correlation_id_var

class CorrelationIdFilter(logging.Filter):
    def filter(self, record):
        record.correlation_id = correlation_id_var.get() or "N/A"
        return True

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    logHandler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s %(correlation_id)s',
        rename_fields={"asctime": "timestamp", "levelname": "level"}
    )
    logHandler.setFormatter(formatter)
    logger.addHandler(logHandler)
    logger.addFilter(CorrelationIdFilter())
