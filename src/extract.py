"""
Extraction module for PEC Archiver.
Handles on-demand extraction of single files from .tar.gz archives
with LRU cache management.
"""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
import logging
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Extraction operation error."""
    pass


class LRUCache:
    """
    LRU (Least Recently Used) cache for extracted files.
    Manages disk space by removing least recently accessed files
    when the cache exceeds the configured size limit.
    """
    
    def __init__(self, cache_path: str, max_size_mb: int = 500):
        """
        Initialize LRU cache.
        
        Args:
            cache_path: Directory path for cached files
            max_size_mb: Maximum cache size in megabytes
        """
        self.cache_path = cache_path
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self._lock = threading.Lock()
        self._access_times: dict[str, float] = {}
        
        # Create cache directory if it doesn't exist
        os.makedirs(cache_path, exist_ok=True)
        
        # Load existing files into access tracking
        self._load_existing_files()
    
    def _load_existing_files(self) -> None:
        """Load existing cached files into access tracking."""
        if not os.path.exists(self.cache_path):
            return
        
        for root, dirs, files in os.walk(self.cache_path):
            for filename in files:
                filepath = os.path.join(root, filename)
                try:
                    # Use file modification time as initial access time
                    mtime = os.path.getmtime(filepath)
                    rel_path = os.path.relpath(filepath, self.cache_path)
                    self._access_times[rel_path] = mtime
                except OSError:
                    pass
    
    def get_cache_path(self, relative_path: str) -> str:
        """
        Get the full cache path for a relative file path.
        
        Args:
            relative_path: Relative path of the file
        
        Returns:
            Full path in the cache directory
        """
        return os.path.join(self.cache_path, relative_path)
    
    def exists(self, relative_path: str) -> bool:
        """
        Check if a file exists in the cache.
        
        Args:
            relative_path: Relative path of the file
        
        Returns:
            True if file exists in cache
        """
        full_path = self.get_cache_path(relative_path)
        return os.path.exists(full_path)
    
    def get(self, relative_path: str) -> Optional[str]:
        """
        Get a file from the cache and update its access time.
        
        Args:
            relative_path: Relative path of the file
        
        Returns:
            Full path to the cached file, or None if not found
        """
        full_path = self.get_cache_path(relative_path)
        
        if os.path.exists(full_path):
            with self._lock:
                self._access_times[relative_path] = time.time()
            return full_path
        
        return None
    
    def put(self, relative_path: str, content: bytes) -> str:
        """
        Store a file in the cache.
        
        Args:
            relative_path: Relative path for the file
            content: File content as bytes
        
        Returns:
            Full path to the cached file
        """
        full_path = self.get_cache_path(relative_path)
        
        # Create parent directories
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        # Write file
        with open(full_path, 'wb') as f:
            f.write(content)
        
        # Update access time
        with self._lock:
            self._access_times[relative_path] = time.time()
        
        # Cleanup if needed
        self._cleanup_if_needed()
        
        return full_path
    
    def _get_cache_size(self) -> int:
        """
        Calculate total size of cached files.
        
        Returns:
            Total size in bytes
        """
        total_size = 0
        
        for root, dirs, files in os.walk(self.cache_path):
            for filename in files:
                filepath = os.path.join(root, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except OSError:
                    pass
        
        return total_size
    
    def _cleanup_if_needed(self) -> None:
        """Remove least recently used files if cache exceeds size limit."""
        current_size = self._get_cache_size()
        
        if current_size <= self.max_size_bytes:
            return
        
        with self._lock:
            # Sort files by access time (oldest first)
            sorted_files = sorted(
                self._access_times.items(),
                key=lambda x: x[1]
            )
            
            # Remove oldest files until under limit
            for rel_path, _ in sorted_files:
                if current_size <= self.max_size_bytes:
                    break
                
                full_path = self.get_cache_path(rel_path)
                try:
                    if os.path.exists(full_path):
                        file_size = os.path.getsize(full_path)
                        os.remove(full_path)
                        current_size -= file_size
                        del self._access_times[rel_path]
                        logger.debug(f"Removed cached file: {rel_path}")
                        
                        # Remove empty parent directories
                        self._cleanup_empty_dirs(os.path.dirname(full_path))
                except OSError as e:
                    logger.warning(f"Failed to remove cached file {rel_path}: {e}")
    
    def _cleanup_empty_dirs(self, dirpath: str) -> None:
        """Remove empty directories up to cache root."""
        while dirpath and dirpath != self.cache_path:
            try:
                if os.path.isdir(dirpath) and not os.listdir(dirpath):
                    os.rmdir(dirpath)
                    dirpath = os.path.dirname(dirpath)
                else:
                    break
            except OSError:
                break
    
    def clear(self) -> None:
        """Clear all cached files."""
        with self._lock:
            for rel_path in list(self._access_times.keys()):
                full_path = self.get_cache_path(rel_path)
                try:
                    if os.path.exists(full_path):
                        os.remove(full_path)
                except OSError:
                    pass
            self._access_times.clear()
            
            # Remove all subdirectories
            for item in os.listdir(self.cache_path):
                item_path = os.path.join(self.cache_path, item)
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path, ignore_errors=True)


# Global cache instance
_cache: Optional[LRUCache] = None


def init_cache(cache_path: str, max_size_mb: int = 500) -> LRUCache:
    """
    Initialize the global cache instance.
    
    Args:
        cache_path: Directory path for cached files
        max_size_mb: Maximum cache size in megabytes
    
    Returns:
        The initialized LRUCache instance
    """
    global _cache
    _cache = LRUCache(cache_path, max_size_mb)
    logger.info(f"Initialized cache at {cache_path} with max size {max_size_mb}MB")
    return _cache


def get_cache() -> Optional[LRUCache]:
    """Get the global cache instance."""
    return _cache


def extract_file_from_archive(
    archive_path: str,
    internal_path: str,
    use_cache: bool = True
) -> str:
    """
    Extract a single file from a .tar.gz archive.
    
    Args:
        archive_path: Path to the .tar.gz archive
        internal_path: Path of the file inside the archive
        use_cache: Whether to use the LRU cache
    
    Returns:
        Path to the extracted file
    
    Raises:
        ExtractionError: If extraction fails
    """
    if not os.path.exists(archive_path):
        raise ExtractionError(f"Archive not found: {archive_path}")
    
    # Generate cache key based on archive path and internal path
    archive_name = os.path.basename(archive_path)
    cache_key = os.path.join(
        os.path.basename(os.path.dirname(archive_path)),  # date dir
        archive_name.replace('.tar.gz', ''),
        internal_path
    )
    
    # Check cache first
    if use_cache and _cache:
        cached_path = _cache.get(cache_key)
        if cached_path:
            logger.debug(f"Cache hit for {internal_path}")
            return cached_path
    
    # Extract from archive
    try:
        with tarfile.open(archive_path, 'r:gz') as tar:
            # Find the member
            member = None
            for m in tar.getmembers():
                if m.name == internal_path or m.name.endswith('/' + internal_path):
                    member = m
                    break
            
            if member is None:
                raise ExtractionError(
                    f"File not found in archive: {internal_path}"
                )
            
            # Extract content
            f = tar.extractfile(member)
            if f is None:
                raise ExtractionError(
                    f"Cannot extract file (may be a directory): {internal_path}"
                )
            
            content = f.read()
            
            # Store in cache if enabled
            if use_cache and _cache:
                extracted_path = _cache.put(cache_key, content)
                logger.debug(f"Cached extracted file: {internal_path}")
                return extracted_path
            else:
                # Write to temp location if cache not available
                temp_dir = tempfile.mkdtemp(prefix='pec_extract_')
                temp_path = os.path.join(temp_dir, os.path.basename(internal_path))
                with open(temp_path, 'wb') as out_f:
                    out_f.write(content)
                return temp_path
                
    except tarfile.TarError as e:
        raise ExtractionError(f"Failed to read archive: {e}")
    except OSError as e:
        raise ExtractionError(f"Failed to extract file: {e}")


def find_archive_in_directory(date_path: str) -> Optional[str]:
    """
    Find the .tar.gz archive file in a date directory.
    
    Args:
        date_path: Path to the date directory
    
    Returns:
        Path to the archive file, or None if not found
    """
    if not os.path.exists(date_path):
        return None
    
    for filename in os.listdir(date_path):
        if filename.endswith('.tar.gz'):
            return os.path.join(date_path, filename)
    
    return None


def get_internal_path(folder: str, filename: str) -> str:
    """
    Construct the internal archive path for a file.
    
    Args:
        folder: Folder name (e.g., INBOX)
        filename: Email filename (e.g., 123_subject.eml)
    
    Returns:
        Internal path in the archive
    """
    return os.path.join(folder, filename)
