"""
Tests for compression module.
"""

import os
import tempfile
import tarfile
import hashlib
import pytest
from datetime import datetime

from src.compression import (
    create_archive,
    create_digest,
    calculate_sha256,
    verify_archive
)


class TestCalculateSha256:
    """Tests for SHA256 calculation."""
    
    def test_calculate_sha256(self):
        """Test SHA256 calculation."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b'test content')
            f.flush()
            
            digest = calculate_sha256(f.name)
            
            # Verify with hashlib directly
            expected = hashlib.sha256(b'test content').hexdigest()
            assert digest == expected
        
        os.unlink(f.name)


class TestCreateArchive:
    """Tests for archive creation."""
    
    def test_create_archive(self):
        """Test creating a tar.gz archive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some test files
            test_file = os.path.join(tmpdir, 'test.txt')
            with open(test_file, 'w') as f:
                f.write('test content')
            
            subdir = os.path.join(tmpdir, 'INBOX')
            os.makedirs(subdir)
            with open(os.path.join(subdir, 'message.eml'), 'w') as f:
                f.write('email content')
            
            # Create archive
            date = datetime(2024, 1, 15)
            archive_path = create_archive(tmpdir, 'testaccount', date)
            
            assert os.path.exists(archive_path)
            assert archive_path.endswith('.tar.gz')
            assert 'testaccount' in archive_path
            assert '2024-01-15' in archive_path
            
            # Verify archive contents
            with tarfile.open(archive_path, 'r:gz') as tar:
                names = tar.getnames()
                assert 'test.txt' in names
                assert 'INBOX' in names
    
    def test_archive_excludes_itself(self):
        """Test that archive excludes itself."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test file
            test_file = os.path.join(tmpdir, 'test.txt')
            with open(test_file, 'w') as f:
                f.write('test')
            
            # Create archive
            date = datetime(2024, 1, 15)
            archive_path = create_archive(tmpdir, 'test', date)
            
            # Verify archive doesn't contain .tar.gz files
            with tarfile.open(archive_path, 'r:gz') as tar:
                names = tar.getnames()
                assert not any(n.endswith('.tar.gz') for n in names)


class TestCreateDigest:
    """Tests for digest creation."""
    
    def test_create_digest(self):
        """Test creating SHA256 digest file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test archive file
            archive_path = os.path.join(tmpdir, 'archive-test-2024-01-15.tar.gz')
            with open(archive_path, 'wb') as f:
                f.write(b'test archive content')
            
            # Create digest
            digest_path = create_digest(archive_path)
            
            assert os.path.exists(digest_path)
            assert digest_path.endswith('.sha256')
            
            # Verify digest content
            with open(digest_path, 'r') as f:
                content = f.read()
            
            expected_hash = calculate_sha256(archive_path)
            assert expected_hash in content
            assert 'archive-test-2024-01-15.tar.gz' in content


class TestVerifyArchive:
    """Tests for archive verification."""
    
    def test_verify_valid_archive(self):
        """Test verifying valid archive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create archive
            archive_path = os.path.join(tmpdir, 'test.tar.gz')
            with open(archive_path, 'wb') as f:
                f.write(b'test content')
            
            # Create digest
            digest_path = create_digest(archive_path)
            
            # Verify
            assert verify_archive(archive_path, digest_path) is True
    
    def test_verify_corrupted_archive(self):
        """Test verifying corrupted archive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create archive
            archive_path = os.path.join(tmpdir, 'test.tar.gz')
            with open(archive_path, 'wb') as f:
                f.write(b'test content')
            
            # Create digest
            digest_path = create_digest(archive_path)
            
            # Corrupt archive
            with open(archive_path, 'wb') as f:
                f.write(b'corrupted content')
            
            # Verify should fail
            assert verify_archive(archive_path, digest_path) is False
