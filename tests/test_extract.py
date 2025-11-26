"""
Tests for extraction module.
"""

import os
import tempfile
import tarfile
import pytest
import time

from src.extract import (
    LRUCache,
    extract_file_from_archive,
    find_archive_in_directory,
    get_internal_path,
    init_cache,
    get_cache,
    ExtractionError
)


class TestLRUCache:
    """Tests for LRU cache."""
    
    @pytest.fixture
    def cache(self):
        """Create a cache with temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = LRUCache(tmpdir, max_size_mb=1)  # 1MB limit for testing
            yield cache
    
    def test_put_and_get(self, cache):
        """Test storing and retrieving files from cache."""
        content = b"test content"
        rel_path = "test/file.eml"
        
        full_path = cache.put(rel_path, content)
        
        assert os.path.exists(full_path)
        assert cache.exists(rel_path)
        
        retrieved_path = cache.get(rel_path)
        assert retrieved_path == full_path
        
        with open(retrieved_path, 'rb') as f:
            assert f.read() == content
    
    def test_get_nonexistent_file(self, cache):
        """Test getting a file that doesn't exist."""
        result = cache.get("nonexistent/file.eml")
        assert result is None
    
    def test_exists(self, cache):
        """Test checking file existence."""
        assert not cache.exists("test/file.eml")
        
        cache.put("test/file.eml", b"content")
        assert cache.exists("test/file.eml")
    
    def test_lru_eviction(self):
        """Test that oldest files are evicted when cache is full."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create cache with 1KB limit
            cache = LRUCache(tmpdir, max_size_mb=0.001)  # ~1KB
            
            # Add files that exceed the limit
            for i in range(10):
                content = b"x" * 200  # 200 bytes each
                cache.put(f"file{i}.eml", content)
                time.sleep(0.01)  # Ensure different access times
            
            # Some files should have been evicted
            existing_files = [f"file{i}.eml" for i in range(10) if cache.exists(f"file{i}.eml")]
            # The most recent files should still exist
            assert len(existing_files) < 10
    
    def test_clear(self, cache):
        """Test clearing the cache."""
        cache.put("file1.eml", b"content1")
        cache.put("file2.eml", b"content2")
        
        assert cache.exists("file1.eml")
        assert cache.exists("file2.eml")
        
        cache.clear()
        
        assert not cache.exists("file1.eml")
        assert not cache.exists("file2.eml")


class TestExtractFileFromArchive:
    """Tests for file extraction from archives."""
    
    @pytest.fixture
    def archive_with_files(self):
        """Create a temporary archive with test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some test files
            inbox_dir = os.path.join(tmpdir, "INBOX")
            os.makedirs(inbox_dir)
            
            email1_path = os.path.join(inbox_dir, "1_test.eml")
            with open(email1_path, 'w') as f:
                f.write("Subject: Test Email 1\n\nBody 1")
            
            email2_path = os.path.join(inbox_dir, "2_test.eml")
            with open(email2_path, 'w') as f:
                f.write("Subject: Test Email 2\n\nBody 2")
            
            # Create archive
            archive_path = os.path.join(tmpdir, "archive-test-2024-01-15.tar.gz")
            with tarfile.open(archive_path, 'w:gz') as tar:
                tar.add(inbox_dir, arcname="INBOX")
            
            # Initialize cache
            cache_dir = os.path.join(tmpdir, "cache")
            os.makedirs(cache_dir)
            init_cache(cache_dir, max_size_mb=10)
            
            yield archive_path, tmpdir
    
    def test_extract_existing_file(self, archive_with_files):
        """Test extracting an existing file from archive."""
        archive_path, tmpdir = archive_with_files
        
        extracted_path = extract_file_from_archive(
            archive_path,
            "INBOX/1_test.eml",
            use_cache=True
        )
        
        assert os.path.exists(extracted_path)
        with open(extracted_path, 'r') as f:
            content = f.read()
        assert "Test Email 1" in content
    
    def test_extract_nonexistent_file(self, archive_with_files):
        """Test extracting a file that doesn't exist in archive."""
        archive_path, _ = archive_with_files
        
        with pytest.raises(ExtractionError) as exc_info:
            extract_file_from_archive(
                archive_path,
                "INBOX/nonexistent.eml",
                use_cache=True
            )
        assert "not found in archive" in str(exc_info.value)
    
    def test_extract_from_nonexistent_archive(self):
        """Test extracting from an archive that doesn't exist."""
        with pytest.raises(ExtractionError) as exc_info:
            extract_file_from_archive(
                "/nonexistent/archive.tar.gz",
                "INBOX/test.eml",
                use_cache=False
            )
        assert "Archive not found" in str(exc_info.value)
    
    def test_cache_hit(self, archive_with_files):
        """Test that cached files are returned on subsequent requests."""
        archive_path, _ = archive_with_files
        
        # First extraction
        path1 = extract_file_from_archive(
            archive_path,
            "INBOX/1_test.eml",
            use_cache=True
        )
        
        # Second extraction should return cached file
        path2 = extract_file_from_archive(
            archive_path,
            "INBOX/1_test.eml",
            use_cache=True
        )
        
        assert path1 == path2


class TestFindArchiveInDirectory:
    """Tests for finding archives in directories."""
    
    def test_find_existing_archive(self):
        """Test finding an archive in a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = os.path.join(tmpdir, "archive-test-2024-01-15.tar.gz")
            with open(archive_path, 'wb') as f:
                f.write(b"dummy archive content")
            
            result = find_archive_in_directory(tmpdir)
            assert result == archive_path
    
    def test_find_no_archive(self):
        """Test when no archive exists in directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = find_archive_in_directory(tmpdir)
            assert result is None
    
    def test_find_in_nonexistent_directory(self):
        """Test finding in a directory that doesn't exist."""
        result = find_archive_in_directory("/nonexistent/path")
        assert result is None


class TestGetInternalPath:
    """Tests for internal path generation."""
    
    def test_get_internal_path(self):
        """Test generating internal archive path."""
        result = get_internal_path("INBOX", "123_subject.eml")
        assert result == "INBOX/123_subject.eml"
    
    def test_get_internal_path_with_special_folder(self):
        """Test generating internal path with special folder name."""
        result = get_internal_path("Posta_inviata", "456_test.eml")
        assert result == "Posta_inviata/456_test.eml"


class TestGlobalCache:
    """Tests for global cache functions."""
    
    def test_init_and_get_cache(self):
        """Test initializing and getting global cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = init_cache(tmpdir, max_size_mb=100)
            
            assert cache is not None
            assert get_cache() is cache
