#!/usr/bin/env python3
"""
PEC Archiver - Main Entry Point

Daily archiving system for Aruba PEC mailboxes.
"""

import sys
import os
import argparse
import logging
from datetime import datetime, timedelta

# Add src to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config, ConfigError
from src.scheduler import PECScheduler


def setup_logging(level: str = 'INFO') -> None:
    """
    Configure logging for the application.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='PEC Archiver - Daily archiving for Aruba PEC mailboxes',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run scheduler (waits for 01:00)
  python -m src.main
  
  # Run immediately for yesterday's emails
  python -m src.main --run-now
  
  # Run for a specific date
  python -m src.main --run-now --date 2024-01-15
  
  # Use custom config file
  python -m src.main --config /path/to/config.yaml
        """
    )
    
    parser.add_argument(
        '--config', '-c',
        type=str,
        default=None,
        help='Path to configuration file (default: uses PEC_ARCHIVE_CONFIG env var)'
    )
    
    parser.add_argument(
        '--run-now', '-r',
        action='store_true',
        help='Run archive job immediately instead of waiting for scheduled time'
    )
    
    parser.add_argument(
        '--date', '-d',
        type=str,
        default=None,
        help='Date to archive (YYYY-MM-DD format, default: yesterday)'
    )
    
    parser.add_argument(
        '--log-level', '-l',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    
    return parser.parse_args()


def main() -> int:
    """
    Main entry point.
    
    Returns:
        Exit code (0 for success, 1 for error)
    """
    args = parse_args()
    
    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    logger.info("PEC Archiver starting...")
    
    # Load configuration
    try:
        config = load_config(args.config)
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    
    # Create scheduler
    scheduler = PECScheduler(config=config)
    
    # Parse target date if provided
    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD")
            return 1
    
    if args.run_now:
        # Run immediately
        logger.info("Running archive job immediately...")
        try:
            report = scheduler.run_once(target_date)
            
            # Print summary
            print("\n" + "="*50)
            print("ARCHIVE JOB COMPLETED")
            print("="*50)
            print(f"Accounts processed: {report['accounts_processed']}")
            print(f"Successful: {report['accounts_successful']}")
            print(f"With errors: {report['accounts_with_errors']}")
            print(f"Total messages: {report['total_messages']}")
            print(f"Total errors: {report['total_errors']}")
            print("="*50 + "\n")
            
            return 0 if report['accounts_with_errors'] == 0 else 1
        except Exception as e:
            logger.error(f"Archive job failed: {e}")
            return 1
    else:
        # Start scheduler
        try:
            scheduler.start()
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            return 0
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            return 1


if __name__ == '__main__':
    sys.exit(main())
