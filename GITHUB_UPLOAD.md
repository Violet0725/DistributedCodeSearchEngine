# 📤 How to Upload to GitHub

## Step 1: Initialize Git Repository

```powershell
# Initialize git repository
git init

# Check status
git status
```

## Step 2: Create GitHub Repository

1. Go to https://github.com/new
2. Repository name: `SearchEngine` (or any name you like)
3. Description: "Distributed Code Search Engine with Semantic Understanding"
4. Choose **Public** or **Private**
5. **DO NOT** check "Initialize with README" (we already have one)
6. Click **"Create repository"**

## Step 3: Add and Commit Files

```powershell
# Add all files
git add .

# Check what will be committed
git status

# Create initial commit
git commit -m "Initial commit: Distributed Code Search Engine with Semantic Understanding"
```

## Step 4: Connect to GitHub

After creating the repo on GitHub, you'll see instructions. Use these commands:

```powershell
# Add remote (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/SearchEngine.git

# Or if you prefer SSH:
# git remote add origin git@github.com:YOUR_USERNAME/SearchEngine.git

# Rename branch to main (if needed)
git branch -M main

# Push to GitHub
git push -u origin main
```

## Step 5: Verify

Go to your GitHub repository page and you should see all your files!

---

## Quick Commands (All in One)

```powershell
# 1. Initialize
git init

# 2. Add files
git add .

# 3. Commit
git commit -m "Initial commit: CodeSearch - Distributed Code Search Engine"

# 4. Add remote (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/SearchEngine.git

# 5. Push
git branch -M main
git push -u origin main
```

---

## What Gets Uploaded

✅ **Included:**
- All source code (`codesearch/`)
- Configuration files (`requirements.txt`, `setup.py`, `pyproject.toml`)
- Documentation (`README.md`)
- Docker files (`docker-compose.yml`, `Dockerfile`)
- Tests (`tests/`)

❌ **Excluded** (via `.gitignore`):
- `venv/` - Virtual environment
- `data/` - Indexed data and repos
- `__pycache__/` - Python cache
- `.env` - Environment variables (sensitive)
- `*.pyc`, `*.pkl` - Generated files

---

## After Uploading

### Add a License (Optional)

```powershell
# Create MIT License file
echo "MIT License" > LICENSE
git add LICENSE
git commit -m "Add MIT License"
git push
```

### Add Topics/Tags on GitHub

On your GitHub repo page, click the gear icon next to "About" and add topics:
- `code-search`
- `semantic-search`
- `vector-database`
- `qdrant`
- `python`
- `nlp`
- `code-analysis`

---

## Troubleshooting

### "Repository not found"
- Check your GitHub username is correct
- Make sure you created the repo on GitHub first

### "Permission denied"
- Use HTTPS and enter your GitHub username/password
- Or set up SSH keys: https://docs.github.com/en/authentication/connecting-to-github-with-ssh

### "Large files"
- If you have large files, GitHub has a 100MB limit
- Large files in `data/` should be ignored by `.gitignore`

