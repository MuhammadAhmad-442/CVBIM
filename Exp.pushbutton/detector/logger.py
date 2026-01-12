# -*- coding: utf-8 -*-
"""
Simple logging utility for consistent output formatting.
"""

class Logger(object):
    """Simple logger with verbosity control."""
    
    VERBOSE = True
    DEBUG = False
    
    @staticmethod
    def info(msg, *args):
        """Log informational message."""
        if Logger.VERBOSE:
            formatted = msg if not args else msg % args
            print("[INFO] {}".format(formatted))
    
    @staticmethod
    def debug(msg, *args):
        """Log debug message."""
        if Logger.DEBUG:
            formatted = msg if not args else msg % args
            print("[DEBUG] {}".format(formatted))
    
    @staticmethod
    def warn(msg, *args):
        """Log warning message."""
        formatted = msg if not args else msg % args
        print("[WARN] {}".format(formatted))
    
    @staticmethod
    def error(msg, *args):
        """Log error message."""
        formatted = msg if not args else msg % args
        print("[ERROR] {}".format(formatted))
    
    @staticmethod
    def section(title):
        """Log section separator."""
        if Logger.VERBOSE:
            print("\n" + "=" * 60)
            print("  {}".format(title))
            print("=" * 60 + "\n")
    
    @staticmethod
    def subsection(title):
        """Log subsection separator."""
        if Logger.VERBOSE:
            print("\n--- {} ---".format(title))