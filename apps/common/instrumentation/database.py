"""
Manual database instrumentation for OpenTelemetry.
Captures database query spans for Django ORM queries.
"""
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode, use_span
from django.db.backends.utils import CursorWrapper
from django.db import connection
import functools
import time


tracer = trace.get_tracer("django.db")


def instrument_database():
    """Instrument Django database connections to create spans for queries."""
    # Wrap the execute method to capture SQL queries
    original_execute = CursorWrapper.execute

    @functools.wraps(original_execute)
    def execute_with_tracing(self, sql, params=None):
        # Skip Django transaction management statements (SAVEPOINT, RELEASE SAVEPOINT)
        sql_upper = sql.upper().strip()
        if sql_upper.startswith("SAVEPOINT") or sql_upper.startswith("RELEASE SAVEPOINT"):
            # Execute without creating a span for transaction management
            return original_execute(self, sql, params)
        
        # Get current span context from TracingMiddleware's start_as_current_span()
        # This ensures database spans are children of HTTP request spans
        current_span = trace.get_current_span()
        if not current_span or not current_span.get_span_context().is_valid:
            # No active span context - execute without tracing (shouldn't happen in normal requests)
            return original_execute(self, sql, params)
        
        # Create span as child of current HTTP request span
        span = tracer.start_span(
            name="db.query",
            attributes={
                "db.system": "postgresql",
                "db.statement": sql[:1000] if len(sql) <= 1000 else sql[:1000] + "...",  # Limit statement length
            },
        )
        
        # Extract operation type from SQL (already have sql_upper from above check)
        if sql_upper.startswith("SELECT"):
            span.set_attribute("db.operation", "SELECT")
        elif sql_upper.startswith("INSERT"):
            span.set_attribute("db.operation", "INSERT")
        elif sql_upper.startswith("UPDATE"):
            span.set_attribute("db.operation", "UPDATE")
        elif sql_upper.startswith("DELETE"):
            span.set_attribute("db.operation", "DELETE")
        else:
            span.set_attribute("db.operation", "OTHER")

        start_time = time.perf_counter()
        try:
            # Use the span as current context
            with use_span(span):
                result = original_execute(self, sql, params)
            span.set_status(Status(StatusCode.OK))
            return result
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        finally:
            duration = (time.perf_counter() - start_time) * 1000  # Convert to milliseconds
            span.set_attribute("db.duration_ms", round(duration, 2))
            span.end()

    # Replace the execute method
    CursorWrapper.execute = execute_with_tracing
    
    # Also wrap executemany for bulk operations
    original_executemany = CursorWrapper.executemany

    @functools.wraps(original_executemany)
    def executemany_with_tracing(self, sql, param_list):
        # Get current span context from TracingMiddleware's start_as_current_span()
        current_span = trace.get_current_span()
        if not current_span or not current_span.get_span_context().is_valid:
            # No active span context - execute without tracing
            return original_executemany(self, sql, param_list)
        
        # Create span as child of current HTTP request span
        span = tracer.start_span(
            name="db.query.executemany",
            attributes={
                "db.system": "postgresql",
                "db.statement": sql[:1000] if len(sql) <= 1000 else sql[:1000] + "...",
                "db.operation": "EXECUTEMANY",
            },
        )
        
        start_time = time.perf_counter()
        try:
            # Use the span as current context
            with use_span(span):
                result = original_executemany(self, sql, param_list)
            span.set_attribute("db.rows_affected", len(param_list))
            span.set_status(Status(StatusCode.OK))
            return result
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        finally:
            duration = (time.perf_counter() - start_time) * 1000
            span.set_attribute("db.duration_ms", round(duration, 2))
            span.end()

    CursorWrapper.executemany = executemany_with_tracing
