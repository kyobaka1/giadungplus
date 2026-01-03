"""
Custom logging handlers for handling Unicode encoding errors gracefully
"""
import sys
import io
import logging
from logging import StreamHandler


class SafeUnicodeStreamHandler(StreamHandler):
    """
    StreamHandler that safely handles Unicode encoding errors.
    This handler will attempt to write Unicode messages and gracefully
    fall back to ASCII with replacement characters if encoding fails.
    """
    def __init__(self, stream=None, encoding='utf-8', errors='replace'):
        """
        Initialize the handler.
        
        Args:
            stream: The stream to write to (default: sys.stdout)
            encoding: The encoding to use (default: 'utf-8')
            errors: How to handle encoding errors (default: 'replace')
        """
        if stream is None:
            stream = sys.stdout
        super().__init__(stream)
        self.encoding = encoding
        self.errors = errors
    
    def emit(self, record):
        """
        Emit a record, handling Unicode encoding errors gracefully.
        """
        try:
            msg = self.format(record)
            stream = self.stream
            
            # Try multiple strategies to write the message
            try:
                # Strategy 1: Direct write (works if stream supports Unicode)
                stream.write(msg + self.terminator)
                stream.flush()
            except UnicodeEncodeError:
                # Strategy 2: Try to encode with UTF-8 and write bytes
                try:
                    if hasattr(stream, 'buffer'):
                        # TextIOWrapper with buffer
                        encoded_msg = (msg + self.terminator).encode(self.encoding, errors=self.errors)
                        stream.buffer.write(encoded_msg)
                        stream.buffer.flush()
                    else:
                        # Fallback: Replace problematic characters
                        safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
                        stream.write(safe_msg + self.terminator)
                        stream.flush()
                except (AttributeError, UnicodeEncodeError, TypeError):
                    # Strategy 3: Last resort - ASCII with replacement
                    try:
                        safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
                        stream.write(safe_msg + self.terminator)
                        stream.flush()
                    except Exception:
                        # If all else fails, try to write a safe error message
                        try:
                            error_msg = f"[Logging Error: Unable to encode message]"
                            stream.write(error_msg + self.terminator)
                            stream.flush()
                        except Exception:
                            pass  # Silently fail if we can't even write error message
            except (AttributeError, TypeError, OSError) as e:
                # Handle other stream errors
                try:
                    safe_msg = msg.encode('ascii', errors='replace').decode('ascii')
                    stream.write(safe_msg + self.terminator)
                    stream.flush()
                except Exception:
                    pass  # Silently fail
        except Exception:
            # Use parent's error handling
            self.handleError(record)


def setup_unicode_safe_streams():
    """
    Setup sys.stdout and sys.stderr to handle Unicode safely.
    This should be called early in the Django startup process.
    """
    try:
        # Only wrap if not already wrapped and encoding is not UTF-8
        if hasattr(sys.stdout, 'encoding') and sys.stdout.encoding != 'utf-8':
            if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
                try:
                    sys.stdout = io.TextIOWrapper(
                        sys.stdout.buffer if hasattr(sys.stdout, 'buffer') else sys.stdout,
                        encoding='utf-8',
                        errors='replace',
                        line_buffering=True
                    )
                except (AttributeError, ValueError):
                    pass
        
        if hasattr(sys.stderr, 'encoding') and sys.stderr.encoding != 'utf-8':
            if not isinstance(sys.stderr, io.TextIOWrapper) or sys.stderr.encoding != 'utf-8':
                try:
                    sys.stderr = io.TextIOWrapper(
                        sys.stderr.buffer if hasattr(sys.stderr, 'buffer') else sys.stderr,
                        encoding='utf-8',
                        errors='replace',
                        line_buffering=True
                    )
                except (AttributeError, ValueError):
                    pass
    except Exception:
        # If wrapping fails, continue without it
        pass

