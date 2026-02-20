import json
import logging
import io
from app.core.logging import setup_logging

def test_json_logging_format():
    """
    Verify that setup_logging configures a JSON formatter that outputs valid JSON.
    """
    # Create a stream to capture logs
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    
    # We need to import our JsonFormatter
    from app.core.logging import JsonFormatter
    handler.setFormatter(JsonFormatter(app="test-app"))
    
    logger = logging.getLogger("test_logger")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False # Don't send to root
    
    # Log something with extra fields
    logger.info("Test message", extra={"user_id": 123, "action": "test"})
    
    # Get the output
    log_output = log_capture.getvalue().strip()
    
    # Verify it's valid JSON
    log_data = json.loads(log_output)
    
    assert log_data["message"] == "Test message"
    assert log_data["user_id"] == 123
    assert log_data["action"] == "test"
    assert log_data["app"] == "test-app"
    assert "timestamp" in log_data
    assert log_data["level"] == "INFO"
    assert log_data["logger"] == "test_logger"

def test_logging_exception_capture():
    """
    Verify that exceptions are correctly captured in JSON logs.
    """
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    from app.core.logging import JsonFormatter
    handler.setFormatter(JsonFormatter())
    
    logger = logging.getLogger("test_exception_logger")
    logger.setLevel(logging.ERROR)
    logger.addHandler(handler)
    logger.propagate = False
    
    try:
        raise ValueError("Something went wrong")
    except ValueError:
        logger.exception("An error occurred")
        
    log_output = log_capture.getvalue().strip()
    log_data = json.loads(log_output)
    
    assert "exception" in log_data
    assert "ValueError: Something went wrong" in log_data["exception"]
    assert log_data["level"] == "ERROR"
