# core/sapo_client/exceptions.py
"""
Custom exceptions for Sapo Client.
"""


class SeleniumLoginInProgressException(Exception):
    """
    Raised when Selenium login is already in progress.
    
    This exception is used to signal that another request is currently
    performing Selenium login, and the current request should wait or
    be redirected to a loading page.
    """
    pass
