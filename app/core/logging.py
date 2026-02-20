import logging
import json
import datetime
import traceback
from typing import Any

class JsonFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    """
    def __init__(self, **kwargs):
        super().__init__()
        self.static_fields = kwargs

    def format(self, record: logging.LogRecord) -> str:
        log_record: dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add static fields
        log_record.update(self.static_fields)

        # Add exception info if present
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        # Add stack trace if requested
        if record.stack_info:
            log_record["stack_info"] = self.formatStack(record.stack_info)

        # Add extra fields passed via 'extra' parameter
        # In standard logging, these are added directly to the record object
        # but are not easily distinguishable from standard attributes.
        # We can look for attributes not in the standard list.
        standard_attrs = {
            'args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
            'funcName', 'levelname', 'levelno', 'lineno', 'module',
            'msecs', 'msg', 'name', 'pathname', 'process', 'processName',
            'relativeCreated', 'stack_info', 'thread', 'threadName'
        }
        
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith('_'):
                log_record[key] = value

        return json.dumps(log_record)

def setup_logging(level=logging.INFO):
    """
    Setup structured JSON logging for the application.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(app="dredge", env="production"))
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicate logs
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
        
    root_logger.addHandler(handler)
    
    # Mute some noisy loggers
    logging.getLogger("uvicorn.access").handlers = [handler]
    logging.getLogger("uvicorn.error").handlers = [handler]
    
    logging.info("Structured JSON logging initialized")
