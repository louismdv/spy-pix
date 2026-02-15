# Vercel KV Setup Instructions

## Step 1: Create a Vercel KV Database

1. Go to your Vercel dashboard: https://vercel.com/dashboard
2. Select your project (or create a new one)
3. Go to the "Storage" tab
4. Click "Create Database"
5. Select "KV" (Key-Value Store)
6. Give it a name (e.g., "spy-pixel-kv")
7. Click "Create"

## Step 2: Connect KV to Your Project

1. After creating the database, click "Connect to Project"
2. Select your spy-pixel project
3. Vercel will automatically add the required environment variable:
   - `REDIS_URL` (or `KV_URL`) - Connection string for your Redis database

The code supports both `REDIS_URL` and `KV_URL` environment variables.

## Step 3: Deploy Your Function

Deploy your project to Vercel:

```bash
vercel deploy
```

Or push to your connected Git repository (GitHub, GitLab, Bitbucket) to trigger automatic deployment.

## Step 4: Test Your Tracking Pixel

After deployment, your tracking pixel URL will be:

```
https://your-project.vercel.app/api/handler?recipient=user@example.com&title=Newsletter
```

Embed this in an email as an image tag:

```html
<img
  src="https://your-project.vercel.app/api/handler?recipient=user@example.com&title=Newsletter"
  width="1"
  height="1"
/>
```

## How It Works

- Email opens are now stored persistently in Vercel KV (Redis)
- Each email is tracked by a unique key: `email:{recipient}:{title}`
- Data includes first open timestamp and total open count
- You'll receive notifications via ntfy.sh when emails are opened

## Troubleshooting

If tracking isn't working:

1. Check environment variables in Vercel dashboard under Settings > Environment Variables
2. Verify `REDIS_URL` (or `KV_URL`) is present
3. Check your Vercel function logs for errors
4. Make sure your IP address is added to `MY_IPS` in handler.py to exclude your own opens
