# Job Lookup Feature

## Overview

Users can now track and recover their jobs even after closing the browser tab or refreshing the page. Jobs can be looked up by **Job ID** or **Email**.

## Features

### 1. Job ID Display

**Location:** Appears when any job is active

**What users see:**
```
ℹ️ Your Job ID: 550e8400-e29b-41d4-a716-446655440000
💡 Copy this ID to check your job status later if you close this tab
```

**Purpose:**
- Users can copy and save their Job ID
- Allows recovery if browser tab is closed
- Works across different devices

### 2. Job Lookup by ID

**Location:** Expander at top of Tool tab: "🔍 Check Job Status by ID or Email"

**How it works:**
1. User selects "Job ID" search method
2. Pastes their Job ID
3. Clicks "Load Job"
4. If found, job loads and shows current status

**User experience:**
```
Search by: ⦿ Job ID  ○ Email

Enter Job ID: [550e8400-e29b-41d4-a716-446655440000]
[Load Job]

✓ Job found! Status: completed
```

### 3. Job Lookup by Email

**Location:** Same expander, select "Email" method

**How it works:**
1. User selects "Email" search method
2. Enters their email address
3. Clicks "Search Jobs"
4. Shows up to 5 most recent jobs
5. User clicks "Load" on any job to view it

**User experience:**
```
Search by: ○ Job ID  ⦿ Email

Enter Email: [user@example.com]
[Search Jobs]

Found 3 job(s)

Job: 550e8400...    Status: completed    [Load]
Job: a1b2c3d4...    Status: running      [Load]
Job: 9876fedc...    Status: failed       [Load]
```

## Implementation Details

### Job Data Structure

**Added field:** `user_email`

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "created_at": "2025-10-06T20:30:08.447091",
  "updated_at": "2025-10-06T20:30:37.055306",
  "user_email": "user@example.com",
  "progress": { ... },
  "result": { ... },
  "error": null
}
```

### Backend Functions

#### `create_job(job_id=None, user_email=None)`
**File:** job_manager.py:43-75

Creates new job with optional email for tracking.

**Changes:**
- Added `user_email` parameter
- Stores email in job data

#### `find_jobs_by_email(email)`
**File:** job_manager.py:179-202

Finds all jobs for a given email address.

**Returns:**
- List of job data dictionaries
- Sorted by `created_at` (newest first)
- Skips corrupted files gracefully

**Performance:**
- Scans all `.jobs/*.json` files
- Simple linear search (fine for moderate volume)
- Could be optimized with indexing if needed

### Frontend UI

#### Job ID Display
**File:** main.py:480-482

Shows prominently when job is active:
```python
st.info(f"**Your Job ID:** `{job_id}`")
st.caption("💡 Copy this ID to check your job status later...")
```

#### Lookup Expander
**File:** main.py:431-472

Collapsible section at top of Tool tab:
- Radio button: Job ID vs Email
- Conditional inputs based on selection
- Search/Load buttons with proper validation

## Use Cases

### Use Case 1: User Closes Tab Accidentally

**Scenario:**
1. User starts long job (20+ PDFs)
2. Accidentally closes browser tab
3. Job continues running in background
4. User panics - "Did I lose my work?"

**Solution:**
1. User opens app again
2. Clicks "🔍 Check Job Status by ID or Email"
3. Selects "Email"
4. Enters email → Finds job
5. Clicks "Load" → Sees job is still running!

### Use Case 2: Checking Job from Different Device

**Scenario:**
1. User starts job on work computer
2. Leaves office before it completes
3. Wants to check status from phone

**Solution:**
1. User saved Job ID when job started
2. Opens app on phone
3. Enters Job ID in lookup
4. Sees job completed, email sent ✓

### Use Case 3: Multiple Jobs Running

**Scenario:**
1. User starts 3 different processing jobs
2. Gets confused which is which
3. Wants to check specific job

**Solution:**
1. Search by email
2. Shows all 3 jobs with status
3. Load any job to see details
4. Each shows different PDFs/variables being processed

## User Benefits

### Before This Feature
- ❌ Page refresh = lost job visibility
- ❌ Close tab = can't check status
- ❌ Multiple jobs = confusion
- ❌ No way to recover if browser crashes

### After This Feature
- ✅ Page refresh = lookup by email
- ✅ Close tab = save Job ID, load later
- ✅ Multiple jobs = view all, load any
- ✅ Browser crash = recover with Job ID

## Technical Notes

### Session State vs Job Files

**Session State:**
- `st.session_state["active_job_id"]`
- Temporary (lost on refresh)
- UI-only tracking

**Job Files:**
- `.jobs/{job_id}.json`
- Persistent (survives refresh/crash)
- True source of truth

**Relationship:**
- Job files are permanent
- Session state just points to current job
- Lookup reconnects session to job file

### Security Considerations

**No authentication:**
- Anyone with Job ID can view job
- Anyone with email can see all jobs for that email

**Current level: Acceptable because:**
- Job IDs are UUIDs (hard to guess)
- Jobs auto-deleted after 24 hours
- No sensitive data in job files (just metadata)

**For production:**
- Consider adding password/auth
- Or time-limited access tokens
- Or email verification before showing jobs

### Performance

**Email search:**
- Scans all job files (O(n))
- Fine for hundreds of jobs
- For thousands: add database/index

**Job ID lookup:**
- Direct file read (O(1))
- Always fast

## Configuration

### Max Jobs Shown

```python
# main.py:459
for job in jobs[:5]:  # Change to show more/fewer
```

### Job Display Format

```python
# main.py:462
st.text(f"Job: {job['job_id'][:8]}...")  # Shows first 8 chars
```

Change to show full ID:
```python
st.text(f"Job: {job['job_id']}")
```

## Error Handling

### Job Not Found by ID
```
❌ Job not found. Check your Job ID.
```

### No Jobs for Email
```
❌ No jobs found for this email
```

### Corrupted Job File
- Skipped silently
- Doesn't crash search
- Logged to console

## Future Enhancements

1. **Job History Table:**
   - Show all jobs in sortable table
   - Filter by status, date
   - Delete old jobs

2. **Job Notifications:**
   - Email when job completes
   - Browser notifications if tab open

3. **Job Sharing:**
   - Share Job ID link with collaborators
   - Read-only view for shared jobs

4. **Job Analytics:**
   - Average processing time
   - Success rate
   - Most common errors

## Testing

### Test Case 1: Lookup by ID
1. Start a job, copy Job ID
2. Refresh page
3. Use lookup with Job ID
4. **Expected:** Job loads, status shown

### Test Case 2: Lookup by Email
1. Start 2-3 jobs with same email
2. Search by email
3. **Expected:** All jobs listed
4. Click "Load" on middle job
5. **Expected:** That specific job loads

### Test Case 3: Invalid Inputs
1. Enter fake Job ID
2. **Expected:** "Job not found" error
3. Enter email with no jobs
4. **Expected:** "No jobs found" error

## Summary

**What this solves:**
- ✅ Users can recover jobs after page refresh
- ✅ Jobs can be tracked across devices
- ✅ Multiple jobs can be managed easily
- ✅ No data loss from accidental tab closures

**Implementation:**
- Simple, no external dependencies
- Uses existing job file infrastructure
- Intuitive UI with clear feedback
- Graceful error handling
