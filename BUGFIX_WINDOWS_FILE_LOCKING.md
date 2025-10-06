# Bug Fix: Windows File Locking Issue

## Problem Description

**Error Message:**
```
[WinError 32] The process cannot access the file because it is being used by another process:
'C:\Users\...\Temp\tmpeuk1z2wv\PR2\AfDBPANPURC_DRC1.pdf'
```

**When it occurred:** When clicking "Run" after uploading a PDF file on Windows.

## Root Cause Analysis

### The Issue

The original implementation used Python's `TemporaryDirectory()` context manager:

```python
with TemporaryDirectory() as temp_dir:
    # Upload PDFs to temp_dir
    # Click "Run" button
    # Start background thread to process PDFs
    # Streamlit reruns (st.rerun())
# <- TemporaryDirectory context exits here
# <- Python tries to delete temp_dir while background thread is still reading files
# <- ERROR: File is locked by another process
```

### Execution Flow That Caused the Bug

1. **Streamlit starts** → Creates `TemporaryDirectory()` context
2. **User uploads PDF** → Saves to `temp_dir`
3. **User clicks "Run"** → Background thread starts, begins reading PDF from `temp_dir`
4. **Streamlit updates UI** → Calls `st.rerun()` to show progress
5. **`st.rerun()` restarts script** → Exits the `with TemporaryDirectory()` block
6. **Python cleanup** → Tries to delete `temp_dir`
7. **Conflict!** → Background thread is still reading files from `temp_dir`
8. **Windows locks files** → Raises `WinError 32`

### Why This is Windows-Specific

- **Windows file locking:** Files cannot be deleted while open by any process
- **Linux/Mac:** More permissive, can delete files while they're open (unlinks inode)
- The bug exists on all platforms but manifests as an error only on Windows

## Solution

### Key Changes

1. **Manual temp directory management** instead of `TemporaryDirectory()` context manager
2. **Persist temp_dir in session state** to prevent premature deletion
3. **Deferred cleanup** using background threads after jobs complete

### Implementation

#### Before (Buggy):
```python
with TemporaryDirectory() as temp_dir:
    build_interface(temp_dir)
    # temp_dir deleted when this block exits, even if threads are using it
```

#### After (Fixed):
```python
# Create temp_dir once and persist in session state
if "temp_dir" not in st.session_state:
    st.session_state["temp_dir"] = mkdtemp(prefix="pdf_processor_")

temp_dir = st.session_state["temp_dir"]
build_interface(temp_dir)

# Cleanup happens ONLY when:
# 1. Job completes successfully
# 2. Job fails
# 3. User starts a new batch
# AND cleanup runs in a background thread with retry logic
```

### Cleanup Strategy

The new `cleanup_temp_dir()` function:

```python
def cleanup_temp_dir(temp_dir_path, max_retries=3, delay=1):
    """
    Safely cleanup temp directory with retry logic for Windows file locking.
    - Retries up to 3 times with 1-second delays
    - Uses background thread to avoid blocking UI
    - Falls back to ignore_errors if all retries fail
    """
```

**When cleanup occurs:**
1. **After job completion:** User clicks "Process Another Batch"
2. **After job failure:** User clicks "Try Again"
3. **Cleanup is deferred** until old jobs finish using the files

## Files Changed

### `main.py`

**Line 47:** Added `mkdtemp` import
```python
from tempfile import TemporaryDirectory, mkdtemp
```

**Line 52:** Added `shutil` import for directory removal
```python
import shutil
```

**Line 55:** Added `threading` import
```python
import threading
```

**Lines 361-385:** Added `cleanup_temp_dir()` function
- Safely removes temp directories
- Retry logic for Windows file locking
- Background execution to avoid blocking

**Lines 403-408:** Changed temp directory lifecycle
```python
# OLD: with TemporaryDirectory() as temp_dir:
# NEW: Persist in session state
if "temp_dir" not in st.session_state:
    st.session_state["temp_dir"] = mkdtemp(prefix="pdf_processor_")
temp_dir = st.session_state["temp_dir"]
```

**Lines 458-465:** Cleanup after job completion
- Creates new temp directory for next batch
- Cleans up old directory in background thread

**Lines 473-480:** Cleanup after job failure
- Same pattern as completion cleanup

## Testing

### Test Case 1: Single PDF Upload
1. Upload a PDF
2. Click "Run"
3. **Expected:** No "WinError 32" error
4. **Expected:** Job processes successfully
5. **Expected:** Progress updates appear

### Test Case 2: Multiple Jobs
1. Upload PDF, click "Run"
2. Wait for completion
3. Click "Process Another Batch"
4. Upload different PDF, click "Run"
5. **Expected:** No errors
6. **Expected:** Old temp directory cleaned up
7. **Expected:** New job uses new temp directory

### Test Case 3: Job Failure Recovery
1. Upload invalid file (trigger failure)
2. Click "Try Again"
3. Upload valid file, click "Run"
4. **Expected:** No errors
5. **Expected:** Cleanup of failed job's temp directory

## Verification

To verify the fix is working:

1. **Check no WinError 32:** Upload PDF and click Run
2. **Check temp directories are created:** Look for `pdf_processor_*` in system temp folder
3. **Check cleanup works:** After job completes, verify old temp directories are removed
4. **Check on Windows:** This is the critical test platform

## Side Effects

### Positive
- ✅ Fixes file locking error on Windows
- ✅ Works on all platforms (Linux, Mac, Windows)
- ✅ Cleanup is deferred until safe
- ✅ Retry logic handles transient file locks

### Potential Issues
- ⚠️ Temp directories persist longer (until cleanup runs)
- ⚠️ If user closes browser before job completes, temp directory remains until next session
- ⚠️ Manual cleanup may be needed for orphaned temp directories

### Mitigation
Consider adding:
1. **Startup cleanup:** Delete old `pdf_processor_*` directories on app start
2. **Scheduled cleanup:** Periodic background task to remove orphaned directories
3. **Max age limit:** Delete temp directories older than N hours

## Future Enhancements

1. **Add startup cleanup:**
```python
# On app startup
import glob
for old_dir in glob.glob("/tmp/pdf_processor_*"):
    if is_older_than(old_dir, hours=24):
        cleanup_temp_dir(old_dir)
```

2. **Track temp directories per session:**
```python
st.session_state["temp_dirs_history"] = []
# Clean all on session end
```

3. **Use Azure Blob Storage** (for production):
   - Eliminates local temp directory issues
   - Better for multi-instance deployments
   - Automatic lifecycle policies

## References

- **Windows file locking:** https://docs.microsoft.com/en-us/windows/win32/fileio/file-locking
- **Python tempfile module:** https://docs.python.org/3/library/tempfile.html
- **Streamlit session state:** https://docs.streamlit.io/library/api-reference/session-state
