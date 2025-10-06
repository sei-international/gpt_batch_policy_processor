# Quick Start: Deploy to Azure with No Timeout Issues

## What Changed?

Your app now uses **background job processing** to avoid Azure's 2-3 minute timeout. Users see real-time progress while jobs run in the background.

## Deploy in 3 Steps

### Step 1: Commit & Push
```bash
git add .
git commit -m "Add async processing for Azure timeout fix"
git push origin main
```

### Step 2: Configure Azure (One-time setup)
1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to: **AI-Policy-Reader** → **Configuration** → **General Settings**
3. Set **Startup Command** to:
   ```
   bash startup.sh
   ```
4. Click **Save**

### Step 3: Wait for Deployment
- GitHub Actions will automatically deploy (5-10 minutes)
- Monitor at: Your GitHub repo → **Actions** tab
- ✅ Green check = Deployed successfully

## Verify It Works

1. Visit: https://ai-policy-reader.azurewebsites.net
2. Upload a small PDF
3. Click "Run"
4. **You should see:**
   - Job starts immediately (no waiting)
   - Progress bars showing PDF/variable processing
   - Updates every 2 seconds
   - Email sent when complete

## What Users Will Experience

### Before (with timeouts ❌)
```
1. Click "Run"
2. Spinner shows "Processing..."
3. Wait 2-3 minutes
4. ERROR: Request timeout
5. No results, no email
```

### After (no timeouts ✅)
```
1. Click "Run"
2. Job starts instantly
3. Progress bars show real-time status
4. Can close browser (job continues)
5. Email received with results
6. Success message in UI
```

## Files Added

- ✅ `job_manager.py` - Background job system
- ✅ `startup.sh` - Azure startup configuration
- ✅ `AZURE_DEPLOYMENT.md` - Full deployment guide
- ✅ `IMPLEMENTATION_SUMMARY.md` - Technical details
- ✅ `.jobs/` directory - Job storage (auto-created)

## Files Modified

- ✅ `main.py` - Added async execution + progress tracking
- ✅ `.gitignore` - Ignore `.jobs/` directory

## Troubleshooting

### "Run button doesn't work"
- Check browser console for errors
- Verify email address is valid
- Ensure PDFs are uploaded correctly

### "Job stuck in 'running' state"
- Check Azure logs: Portal → Log Stream
- Verify OpenAI API key is configured
- Check `.jobs/<job-id>.json` for error details

### "No progress updates"
- Refresh the page
- Check internet connection
- Verify Streamlit is running (Azure logs)

## Need Help?

📧 Email: aipolicyreader@sei.org

📖 Full docs: See `AZURE_DEPLOYMENT.md`

## Technical Details

Want to understand how it works? Read:
- `IMPLEMENTATION_SUMMARY.md` - Architecture & design decisions
- `AZURE_DEPLOYMENT.md` - Deployment & configuration
- `job_manager.py` - Source code with comments
