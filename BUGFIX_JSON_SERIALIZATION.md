# Bug Fix: JSON Serialization Error

## Problem Description

**Error Message:**
```
Error processing PDFs: Expecting value: line 15 column 5 (char 371)
Error generating output document: Expecting value: line 15 column 5 (char 371)
```

**When it occurred:** Immediately after clicking "Run" button.

## Root Cause Analysis

### The Issue

The error was a **JSON parsing error** when reading job status files from `.jobs/` directory.

**Investigation Steps:**

1. **Checked job files** in `.jobs/` directory
2. **Found corrupted JSON files**:
```json
{
  "job_id": "7e0b0411-cb79-4784-a13c-2b141c4503b0",
  "status": "completed",
  ...
  "result": [
    74,
```
Notice the incomplete array ending with `74,` - this is **invalid JSON**.

3. **Traced the source**: The `main()` function was returning data that couldn't be serialized to JSON

### Root Cause

In `main.py:360`, the function returned:
```python
return total_num_pages, output_doc, None
```

This tuple contains:
- `total_num_pages` - integer ✓ (JSON serializable)
- `output_doc` - **openpyxl Workbook object** ❌ (NOT JSON serializable!)
- `None` - null ✓ (JSON serializable)

When `job_manager.py:211` tried to save this result:
```python
result = target_func(*args, **kwargs)  # Returns the tuple above
job_manager.mark_completed(job_id, result)  # Tries to save as JSON
```

The `json.dump()` in `job_manager.py:175` failed because **Workbook objects can't be serialized to JSON**. This left the job file partially written and corrupted.

### Why the Error Occurred

1. Job starts → Creates `.jobs/<uuid>.json`
2. Job completes → Calls `mark_completed(job_id, result)`
3. `mark_completed()` tries to save result to JSON
4. `json.dump()` fails partway through (Workbook not serializable)
5. Job file left corrupted with incomplete JSON
6. Next time app loads → Tries to read corrupted JSON
7. **Error: "Expecting value: line 15 column 5"**

## Solution

### Key Change

Fixed `main()` to return a **JSON-serializable dictionary** instead of a tuple with non-serializable objects.

### Implementation

#### Before (Buggy):
```python
# main.py:360
return total_num_pages, output_doc, None  # Workbook not JSON serializable!
```

#### After (Fixed):
```python
# main.py:348-361
result = {
    "total_num_pages": total_num_pages,
    "output_file_size": len(output_file_contents),
    "num_pdfs": len(gpt_analyzer.pdfs),
    "failed_pdfs": failed_pdfs
}
return result  # All values are JSON serializable
```

### Additional Fix

Also fixed error handling to properly raise exceptions:

#### Before:
```python
except Exception as e:
    return total_num_pages, output_doc, e  # Wrong - returns tuple
```

#### After:
```python
except Exception as e:
    raise e  # Correct - lets job_manager handle it
```

## Files Changed

### `main.py`

**Lines 348-361:** Changed return value
```python
# OLD:
return total_num_pages, output_doc, None

# NEW:
result = {
    "total_num_pages": total_num_pages,
    "output_file_size": len(output_file_contents),
    "num_pdfs": len(gpt_analyzer.pdfs),
    "failed_pdfs": failed_pdfs
}
return result
```

**Line 323-324:** Changed error handling
```python
# OLD:
return total_num_pages, output_doc, e

# NEW:
raise e
```

### Cleanup

Removed all corrupted job files:
```bash
rm -f .jobs/*.json
```

## Verification

### What Was Wrong

1. **Job files were corrupted** - incomplete JSON
2. **Workbook objects can't be JSON serialized**
3. **Return value was wrong type**

### What's Fixed

1. ✅ `main()` returns JSON-serializable dict
2. ✅ Job files save successfully
3. ✅ Job status can be read without errors
4. ✅ Errors properly propagate to job_manager

## Testing

### Test Case 1: Successful Job
1. Upload PDF
2. Click "Run"
3. **Expected:** Job completes, status file created successfully
4. **Expected:** No JSON parsing errors
5. **Expected:** Check `.jobs/<uuid>.json` - should be valid JSON

### Test Case 2: Failed Job
1. Upload invalid file
2. Click "Run"
3. **Expected:** Job marked as failed
4. **Expected:** Error stored in job file
5. **Expected:** Job file is valid JSON

### Test Case 3: Job Status Reading
1. Complete a job
2. Refresh page
3. **Expected:** Previous job status loads correctly
4. **Expected:** No "Expecting value" errors

## Why This Matters

### Before Fix
- ❌ Job files corrupted after every run
- ❌ JSON parsing errors on subsequent loads
- ❌ App couldn't track job progress
- ❌ Users saw cryptic "Expecting value" errors

### After Fix
- ✅ Job files save correctly
- ✅ Job status persists properly
- ✅ Progress tracking works
- ✅ No JSON errors

## Prevention

### What to Watch For

When modifying `main()` function:
- **Always return JSON-serializable data**
- **Don't return objects** (Workbooks, DataFrames, etc.)
- **Use dictionaries with primitive types**: str, int, float, bool, list, dict, None

### Valid Return Types
```python
# ✅ GOOD - All JSON serializable
return {
    "count": 42,
    "name": "test",
    "success": True,
    "items": [1, 2, 3],
    "metadata": {"key": "value"}
}

# ❌ BAD - Contains non-serializable objects
return {
    "workbook": openpyxl.Workbook(),  # Not JSON serializable
    "dataframe": pd.DataFrame(),       # Not JSON serializable
    "exception": Exception()            # Not JSON serializable
}
```

## Related Issues

This same pattern could cause issues in:
- Any function called via `run_job_async()`
- Any data stored in job state files
- Any API endpoints returning complex objects

## Future Enhancements

Consider adding:
1. **JSON serialization validation** in `job_manager.py`
2. **Type hints** to document expected return types
3. **Automated tests** for job file integrity
4. **Better error messages** when serialization fails

## References

- Python JSON module: https://docs.python.org/3/library/json.html
- Openpyxl Workbook docs: https://openpyxl.readthedocs.io/
- Job manager implementation: `job_manager.py:211`
