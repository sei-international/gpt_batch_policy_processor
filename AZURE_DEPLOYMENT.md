# Azure Web App Deployment Guide

## Overview

This application has been modified to support asynchronous background processing, preventing Azure Web App timeout issues for long-running PDF processing tasks.

## Key Changes

### 1. **Background Job Processing**
- Added `job_manager.py` module to handle async job execution
- Jobs run in background threads, independent of HTTP request timeouts
- File-based job state persistence in `.jobs/` directory

### 2. **Real-time Progress Tracking**
- Users see live progress updates while jobs run
- Progress bars show PDF and variable processing status
- Automatic polling every 2 seconds for status updates

### 3. **Email-first Results Delivery**
- Results are always emailed to users (existing functionality)
- Users can safely close browser while jobs run
- No timeout issues regardless of processing duration

## Azure Configuration

### Required Application Settings

In the Azure Portal, configure these settings for your Web App:

1. **Navigate to:** Azure Portal → Your Web App → Configuration → Application Settings

2. **Add/verify these settings:**

```
SCM_DO_BUILD_DURING_DEPLOYMENT = true
WEBSITE_TIME_ZONE = UTC
```

3. **Startup Command:**
```bash
bash startup.sh
```

Or in Azure Portal:
- Navigate to: Configuration → General Settings → Startup Command
- Enter: `bash startup.sh`

### File System Configuration

The application uses file-based job storage in the `.jobs/` directory. Ensure:

1. The app has write permissions to its working directory
2. The `.jobs/` directory is created automatically on startup (handled by `startup.sh`)

## Deployment Steps

### Via GitHub Actions (Recommended)

This repository includes `.github/workflows/main_ai-policy-reader.yml` which automatically deploys to Azure when you push to the `main` branch.

**To deploy:**

1. Commit your changes to the repository
2. Push to the `main` branch:
   ```bash
   git add .
   git commit -m "Add async job processing for Azure deployment"
   git push origin main
   ```
3. GitHub Actions will automatically build and deploy to Azure
4. Monitor deployment at: GitHub → Actions tab

### Manual Deployment (Alternative)

If you prefer manual deployment:

```bash
# Login to Azure
az login

# Deploy
az webapp up --name AI-Policy-Reader --resource-group <your-resource-group>
```

## How It Works

### User Experience Flow

1. **User clicks "Run"**
   - Job is created immediately
   - HTTP request completes in <1 second
   - Background thread starts processing

2. **Processing runs in background**
   - User sees real-time progress updates
   - Progress bars show PDF/variable completion
   - Status messages indicate current operation

3. **Job completes**
   - Results emailed to user automatically
   - Success message displayed in UI
   - User can process another batch

### Technical Architecture

```
┌─────────────────┐
│  User Browser   │
│   (Streamlit)   │
└────────┬────────┘
         │ Click "Run"
         ▼
┌─────────────────┐
│  HTTP Request   │ ← Returns immediately
│  (Create Job)   │    (No timeout!)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Background      │
│ Thread Pool     │ ← Runs independently
│ (job_manager)   │    No HTTP timeout
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ File-based      │
│ Job State       │ ← Stores in .jobs/
│ (.jobs/*.json)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Email Results   │ ← Existing functionality
│ (Resend API)    │
└─────────────────┘
```

## Monitoring & Troubleshooting

### Check Job Status

Jobs are stored as JSON files in `.jobs/` directory:
- Each job has a unique ID (UUID)
- Job files contain status, progress, results, and errors

### View Logs

In Azure Portal:
1. Navigate to: Your Web App → Log Stream
2. Or use: `az webapp log tail --name AI-Policy-Reader --resource-group <your-resource-group>`

### Common Issues

**Issue: Jobs not starting**
- Check: Azure logs for startup errors
- Verify: `.jobs/` directory has write permissions
- Ensure: `startup.sh` is executable

**Issue: Progress not updating**
- Check: Browser console for errors
- Verify: Streamlit is running with correct port (8000)
- Ensure: Auto-refresh is working (2-second interval)

**Issue: Jobs stuck in "running" state**
- Check: Application logs for Python exceptions
- Verify: OpenAI API key is configured correctly
- Review: Job error details in `.jobs/<job-id>.json`

## Cleanup & Maintenance

### Automatic Cleanup

The job manager includes automatic cleanup of old jobs:
- Default: Jobs older than 24 hours are removed
- Can be configured in `job_manager.py`

### Manual Cleanup

To manually clean up old job files:

```bash
# SSH into Azure Web App
az webapp ssh --name AI-Policy-Reader --resource-group <your-resource-group>

# Remove old job files
rm -rf .jobs/*.json
```

## Performance Considerations

### Threading

- Uses Python's `threading` module (no external dependencies)
- Daemon threads ensure they don't block app shutdown
- Multiple jobs can run concurrently

### File-based Storage

- Simple, no external dependencies (Redis, etc.)
- Suitable for moderate job volumes
- For high-volume production, consider Redis/database

### Scaling

Current implementation supports:
- ✅ Single Azure Web App instance
- ✅ Moderate concurrent jobs (10-50)
- ⚠️ Multiple instances require shared storage (e.g., Azure Blob Storage)

For multi-instance deployments, modify `job_manager.py` to use Azure Blob Storage instead of local filesystem.

## Testing

### Local Testing

Test the async functionality locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Run Streamlit
streamlit run main.py
```

Upload a PDF and verify:
1. Job starts immediately
2. Progress updates appear
3. Email is sent on completion

### Production Testing

After deploying to Azure:

1. Navigate to: https://ai-policy-reader.azurewebsites.net
2. Upload a small PDF (1-5 pages)
3. Submit with 1-3 variables
4. Verify progress tracking works
5. Confirm email delivery

## Support

For issues specific to this deployment:
- Check Azure logs first
- Review job state files in `.jobs/`
- Verify environment variables are set correctly

For application-specific issues:
- Contact: aipolicyreader@sei.org
